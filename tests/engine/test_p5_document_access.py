"""HTTP document views require local permission even for a model-purpose snapshot."""

import hashlib

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from researchgraph.external_document_api import register_external_document_api
from researchgraph.external_documents import read_external_document
from researchgraph.knowledge_models import AuthorizedRoot
from researchgraph.knowledge_store import KnowledgeError, KnowledgeStore, text_hash
from researchgraph.models import Chunk
from researchgraph.p5_personal import set_annotation_grant
from researchgraph.wiki_store import read_page
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_external_documents import register, request
from test_external_documents import source as source
from test_p5_personal import _saved_personal_wiki, grant
from test_p5_personal import personal as personal
from test_p5_personal import seeded as seeded
from test_query_documents import engine as engine


def revoke(engine, source_kind, *, allow_local, allow_model):
    with Session(engine) as session, session.begin():
        if source_kind == "annotation":
            set_annotation_grant(
                KnowledgeStore(session),
                "project",
                "annotation",
                allow_model,
                1,
                "api-purpose-revocation",
                allow_local=allow_local,
            )
        else:
            KnowledgeStore(session).query().set_note_grant(
                "project", "root", allow_local, allow_model
            )


@pytest.mark.parametrize("source_kind", ["annotation", "user_view", "external_source"])
@pytest.mark.parametrize(
    "purpose,allow_local,allow_model,visible",
    [
        ("model", False, True, False),
        ("model", True, False, False),
        ("local", False, True, False),
        ("local", True, False, True),
    ],
)
def test_wiki_http_read_checks_both_uses_without_changing_internal_model_reads(
    personal, source_kind, purpose, allow_local, allow_model, visible
):
    api, engine, root = personal
    if source_kind == "annotation":
        grant(engine)
    _, saved = _saved_personal_wiki(engine, source_kind, root)
    revoke(engine, source_kind, allow_local=allow_local, allow_model=allow_model)
    response = api.get(
        f"/api/v1/projects/project/wiki/pages/{saved['page_id']}",
        params={"purpose": purpose, "include_personal": True},
    )
    assert response.status_code == 200, response.text
    assert ("PRIVATE-COMPAT-WIKI" in response.text) is visible
    if not visible:
        assert "EXTERNAL-ROOT-COMPAT-SECRET" not in response.text
        assert "My private question" not in response.text
        assert not response.json()["diff"]
        assert all(not section["text"] for section in response.json()["sections"])
        assert not response.json()["versions"]
    if allow_model and not allow_local:
        with Session(engine) as session:
            internal = read_page(
                session, "project", saved["page_id"], include_personal=True, purpose="model"
            )
            assert "PRIVATE-COMPAT-WIKI" in internal["markdown"]


@pytest.mark.parametrize("source_kind", ["annotation", "external_source"])
def test_wiki_http_diff_and_history_do_not_reveal_a_locally_revoked_private_base(
    personal, source_kind
):
    api, engine, root = personal
    if source_kind == "annotation":
        grant(engine)
    _, saved = _saved_personal_wiki(engine, source_kind, root)
    with Session(engine) as session, session.begin():
        before = read_page(session, "project", saved["page_id"], include_personal=True)
        chunk = session.scalar(select(Chunk))
        changed = (
            KnowledgeStore(session)
            .wiki()
            .apply_patch(
                "project",
                saved["page_id"],
                {
                    "base_version_id": saved["version_id"],
                    "base_content_hash": saved["content_hash"],
                    "operations": [
                        {
                            "op": "replace",
                            "section_id": before["sections"][0]["section_id"],
                            "passage": {
                                "heading": "Public replacement",
                                "text": "PUBLIC-CURRENT-WIKI",
                                "attribution": "paper_author",
                                "dependencies": [
                                    {
                                        "type": "chunk",
                                        "id": chunk.id,
                                        "sha256": text_hash(chunk.text),
                                        "start": 0,
                                        "end": len(chunk.text),
                                        "quote": chunk.text,
                                    }
                                ],
                                "caveats": [],
                                "conditions": [],
                                "links": [],
                            },
                        }
                    ],
                },
                "public-head-private-base",
            )
        )
        assert (
            "PRIVATE-COMPAT-WIKI"
            in read_page(session, "project", saved["page_id"], include_personal=True)["diff"]
        )
    revoke(engine, source_kind, allow_local=False, allow_model=True)
    response = api.get(
        f"/api/v1/projects/project/wiki/pages/{saved['page_id']}",
        params={"purpose": "model", "include_personal": True},
    )
    assert response.status_code == 200, response.text
    assert "PUBLIC-CURRENT-WIKI" in response.text
    assert "PRIVATE-COMPAT-WIKI" not in response.text
    assert not response.json()["diff"]
    assert {v["version_id"] for v in response.json()["versions"]} == {changed["version_id"]}
    historical = api.get(
        f"/api/v1/projects/project/wiki/pages/{saved['page_id']}",
        params={
            "purpose": "model",
            "include_personal": True,
            "version_id": saved["version_id"],
        },
    )
    assert "PRIVATE-COMPAT-WIKI" not in historical.text


@pytest.mark.parametrize("revoked_use", ["local", "model"])
def test_external_http_history_checks_each_versions_root_for_both_uses(
    engine, source, tmp_path, revoked_use
):
    first = register(engine, request(source, title="PRIVATE-OLD-TITLE"))
    current_root = tmp_path / "public-current-root"
    current_root.mkdir()
    current_file = current_root / "current.md"
    current_file.write_text("CURRENT-EXTERNAL-TEXT", encoding="utf-8")
    with Session(engine) as session, session.begin():
        session.add(
            AuthorizedRoot(
                id="current-root",
                project_id="p",
                path=str(current_root),
                active=True,
                created_at="now",
            )
        )
        session.flush()
        store = KnowledgeStore(session)
        store.query().set_note_grant("p", "root", True, True)
        store.query().set_note_grant("p", "current-root", True, True)
    second = register(
        engine,
        {
            "root_id": "current-root",
            "relative_path": "current.md",
            "expected_sha256": hashlib.sha256(current_file.read_bytes()).hexdigest(),
            "title": "CURRENT-TITLE",
            "attribution": "external_source",
            "document_id": first["document_id"],
            "base_version_id": first["version_id"],
        },
        "external-second-root",
    )
    with Session(engine) as session, session.begin():
        KnowledgeStore(session).query().set_note_grant(
            "p", "root", revoked_use != "local", revoked_use != "model"
        )
    app = FastAPI()

    @app.exception_handler(KnowledgeError)
    async def error_response(_request, error):
        return JSONResponse(status_code=409, content={"code": error.code})

    register_external_document_api(app, lambda: engine)
    with TestClient(app) as api:
        url = f"/api/v1/projects/p/external-documents/{first['document_id']}"
        current = api.get(url, params={"include_personal": True, "purpose": "model"})
        assert current.status_code == 200, current.text
        assert current.json()["text"] == "CURRENT-EXTERNAL-TEXT"
        assert "PRIVATE-OLD-TITLE" not in current.text
        assert [v["version_id"] for v in current.json()["versions"]] == [second["version_id"]]
        old = api.get(
            url,
            params={
                "include_personal": True,
                "purpose": "model",
                "version_id": first["version_id"],
            },
        )
        assert old.status_code == 409
        assert old.json()["code"] == "EXTERNAL_SOURCE_NOT_AUTHORIZED"
        assert first["text"] not in old.text and "PRIVATE-OLD-TITLE" not in old.text
    if revoked_use == "local":
        with Session(engine) as session:
            internal = read_external_document(
                session,
                "p",
                first["document_id"],
                first["version_id"],
                include_personal=True,
                purpose="model",
            )
            assert internal["text"] == first["text"]
            assert "PRIVATE-OLD-TITLE" in str(internal["versions"])

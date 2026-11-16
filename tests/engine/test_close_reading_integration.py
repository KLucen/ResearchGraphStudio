"""Public app/worker integration with an isolated, deterministic Provider."""

import json
from uuid import uuid4

from researchgraph.core import text_hash
from researchgraph.models import AttachmentRevision, Chunk, EvidenceSpan, Paper, Section, now
from sqlalchemy.orm import Session
from test_engine import client, post
from test_ingest import FIXTURES, queue, wait_job


class ReadingProvider:
    name = "integration-provider"
    model = "integration-model"
    base_url = "https://provider.test/v1"
    parameters: dict = {}

    def __init__(self, *, partial_once: bool = False):
        self.calls = 0
        self.partial_once = partial_once
        self.usage = {"prompt_tokens": 23, "completion_tokens": 41, "total_tokens": 64}
        self.request_metadata: dict = {}
        self.inputs: list[dict] = []

    async def complete(self, prompt, data, schema):
        self.calls += 1
        self.inputs.append(data)
        if "user_explanation" in data:
            return json.dumps(
                {
                    "check_result": "PARTIAL",
                    "correct_points_zh": ["识别了方法输入"],
                    "missing_or_mistaken_zh": ["补充适用条件"],
                    "feedback_zh": "复述基本忠于本段，但范围有限。",
                    "follow_up_question_zh": "方法在什么条件下适用？",
                }
            )
        paragraphs = data["paragraphs"]
        if self.partial_once and self.calls == 1:
            paragraphs = paragraphs[:1]
        return json.dumps(
            {
                "schema_version": "section_reading_analysis.v1",
                "paragraphs": [
                    {
                        "paragraph_id": p["paragraph_id"],
                        "translation_zh": f"第 {i + 1} 段的合成中文译文。",
                        "paragraph_function": "EXPLAIN_METHOD",
                        "logic_role_zh": "说明当前方法的输入。",
                        "critical_note_zh": "核查适用条件。",
                        "reading_question_zh": None,
                        "highlights": [
                            {"type": "METHOD", "quote_en": p["text_en"][:8], "occurrence_index": 0}
                        ],
                        "related_graph_node_ids": [],
                    }
                    for i, p in enumerate(paragraphs)
                ],
                "section_argument": {
                    "logic_chain_zh": ["提出方法", "说明输入"],
                    "core_claim_zh": "仅合成测试范围",
                    "strong_point_zh": None,
                    "question_to_verify_zh": "适用条件是什么？",
                },
            }
        )


def configure(monkeypatch, provider):
    monkeypatch.setattr(
        "researchgraph.model_settings.snapshot_for",
        lambda *_: {
            "provider": provider.name,
            "model": provider.model,
            "base_url": provider.base_url,
            "parameters": provider.parameters,
        },
    )
    monkeypatch.setattr("researchgraph.model_settings.from_snapshot", lambda *_: provider)


def generate(api, scope, revision, paragraphs, **extra):
    response = post(
        api,
        f"{scope}/close-reading/generate",
        {
            "document_version_id": revision,
            "paragraph_ids": paragraphs,
            "allow_network": True,
            **extra,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_public_worker_local_import_cache_check_and_restart(tmp_path, monkeypatch):
    provider = ReadingProvider()
    configure(monkeypatch, provider)
    fixture_hash = text_hash((FIXTURES / "two-pages.pdf").read_bytes().hex())
    with client(tmp_path, worker=True) as api:
        project = post(api, "/projects", {"name": "Reading integration"}).json()["id"]
        imported = wait_job(api, queue(api, project, FIXTURES / "two-pages.pdf", "reading-import"))
        assert imported["status"] == "succeeded", imported
        paper, revision = (imported["result"][key] for key in ("paper_id", "revision_id"))
        sections = api.get(f"/api/v1/revisions/{revision}/sections").json()["sections"]
        section = next(item for item in sections if not item["excluded"] and item["chunk_ids"])
        scope = f"/papers/{paper}/sections/{section['id']}"
        paragraphs = api.get(f"/api/v1{scope}/paragraphs").json()["paragraphs"]
        selected = [paragraphs[0]["paragraph_id"]]
        state = {
            "document_version_id": revision,
            "progress": "READING",
            "self_assessment": "PARTIAL",
        }
        assert api.put(f"/api/v1{scope}/reading-state", json=state).status_code == 200
        assert api.get(f"/api/v1{scope}/close-reading").json() is None
        assert api.get(f"/api/v1/papers/{paper}/concept-understanding").json() == []
        assert provider.calls == 0
        assert api.get(f"/api/v1/projects/{project}/lite/usage").json()["calls"] == 0

        queued = generate(api, scope, revision, selected)
        job = wait_job(api, {"id": queued["job_id"]})
        assert job["status"] == "succeeded", job
        completed = api.get(f"/api/v1{scope}/close-reading?result_id={queued['id']}").json()
        assert completed["status"] == "COMPLETED"
        assert completed["analysis"]["paragraphs"][0]["translation_zh"]
        assert completed["usage"]["input_tokens"] == 23
        cached = generate(api, scope, revision, selected)
        assert cached["cache_hit"] is True
        assert provider.calls == 1
        assert "text_en" not in completed["analysis"]["paragraphs"][0]
        checked = post(
            api,
            f"{scope}/understanding-check",
            {
                "document_version_id": revision,
                "paragraph_ids": selected,
                "allow_network": True,
                "user_explanation": "The method defines a limited input.",
            },
        )
        assert checked.status_code == 200, checked.text
        assert wait_job(api, {"id": checked.json()["job_id"]})["status"] == "succeeded"
        assert (
            api.get(f"/api/v1{scope}/understanding-check").json()["check"]["check_result"]
            == "PARTIAL"
        )
        assert api.get(f"/api/v1{scope}/reading-state").json()["self_assessment"] == "PARTIAL"
        assert provider.calls == 2
        usage = api.get(f"/api/v1/projects/{project}/lite/usage").json()
        assert usage["calls"] == 2 and usage["input_tokens"] == 46 and usage["output_tokens"] == 82
    with client(tmp_path) as reopened:
        restored = reopened.get(f"/api/v1{scope}/close-reading?result_id={queued['id']}")
        assert restored.status_code == 200 and restored.json()["status"] == "COMPLETED"
        assert reopened.get(f"/api/v1{scope}/reading-state").json()["progress"] == "READING"
        assert provider.calls == 2
    assert text_hash((FIXTURES / "two-pages.pdf").read_bytes().hex()) == fixture_hash


def seed_range(api):
    project = post(api, "/projects", {"name": "Partial integration"}).json()["id"]
    paper, revision, section = (str(uuid4()) for _ in range(3))
    paragraphs = [str(uuid4()), str(uuid4())]
    with Session(api.app.state.engine) as session, session.begin():
        session.add(Paper(id=paper, project_id=project, title="Synthetic", created_at=now()))
        session.flush()
        session.add(
            AttachmentRevision(
                id=revision,
                paper_id=paper,
                sha256="a" * 64,
                parser_version="test",
                page_count=1,
                warnings=[],
                created_at=now(),
            )
        )
        session.flush()
        session.add(
            Section(
                id=section,
                document_version_id=revision,
                title="Method",
                ordinal=1,
                role="method",
                parser="test",
                parent_id=None,
                level=1,
                start_page=0,
                end_page=0,
                excluded=False,
            )
        )
        session.flush()
        for index, paragraph in enumerate(paragraphs):
            text = f"The method uses input number {index + 1}."
            session.add(
                Chunk(
                    id=paragraph,
                    revision_id=revision,
                    page_index=0,
                    page_label="1",
                    block_index=index,
                    text=text,
                    bbox=[0, 0, 1, 1],
                )
            )
            session.flush()
            session.add(
                EvidenceSpan(
                    id=str(uuid4()),
                    document_version_id=revision,
                    section_id=section,
                    paragraph_id=paragraph,
                    page_index=0,
                    start_offset=0,
                    end_offset=len(text),
                    quote=text,
                    text_sha256=text_hash(text),
                    normalization="identity-v1",
                    bbox_list=[[0, 0, 1, 1]],
                )
            )
    return project, paper, revision, section, paragraphs


def test_partial_public_history_missing_retry_and_reopen(tmp_path, monkeypatch):
    provider = ReadingProvider(partial_once=True)
    configure(monkeypatch, provider)
    with client(tmp_path, worker=True) as api:
        project, paper, revision, section, paragraphs = seed_range(api)
        scope = f"/papers/{paper}/sections/{section}"
        queued = generate(api, scope, revision, paragraphs)
        failed = wait_job(api, {"id": queued["job_id"]})
        assert failed["status"] == "failed" and failed["stage"] == "failed"
        assert api.get(f"/api/v1/projects/{project}/jobs").status_code == 200
        assert post(api, f"/jobs/{failed['id']}/retry").status_code == 409
        partial = api.get(f"/api/v1{scope}/close-reading?result_id={queued['id']}").json()
        assert partial["status"] == "INCOMPLETE"
        assert partial["missing_paragraph_ids"] == paragraphs[1:]
        assert len(partial["analysis"]["paragraphs"]) == 1
        repair = generate(api, scope, revision, paragraphs[1:], retry_missing_of=queued["id"])
        assert wait_job(api, {"id": repair["job_id"]})["status"] == "succeeded"
        restored = api.get(f"/api/v1{scope}/close-reading?result_id={queued['id']}").json()
        assert restored["status"] == "COMPLETED" and restored["missing_paragraph_ids"] == []
        assert [p["paragraph_id"] for p in restored["analysis"]["paragraphs"]] == paragraphs
        assert provider.inputs[1]["paragraphs"][0]["paragraph_id"] == paragraphs[1]
        assert len(provider.inputs[1]["paragraphs"]) == 1 and provider.calls == 2
        assert restored["usage"]["calls"] == 2
    with client(tmp_path) as reopened:
        restored = reopened.get(f"/api/v1{scope}/close-reading?result_id={queued['id']}").json()
        assert restored["status"] == "COMPLETED" and len(restored["analysis"]["paragraphs"]) == 2
        assert provider.calls == 2

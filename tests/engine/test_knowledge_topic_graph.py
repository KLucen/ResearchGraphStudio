from uuid import uuid4

from researchgraph.archive_api import archive_target
from researchgraph.knowledge_library import ensure_library
from researchgraph.knowledge_library_models import (
    KnowledgeCollection,
    KnowledgeCollectionMember,
    LibraryPaper,
    PaperKnowledgeVersion,
)
from researchgraph.models import Job
from sqlalchemy.orm import Session
from test_engine import client


def test_topic_context_returns_only_bounded_current_outside_papers(tmp_path):
    with client(tmp_path) as api:
        engine = api.app.state.engine
        collection_id = str(uuid4())
        expected = []
        with Session(engine) as db, db.begin():
            library = ensure_library(db)
            db.add(KnowledgeCollection(id=collection_id, library_id=library.id, name="专题"))
            db.flush()
            for index in range(16):
                paper_id, version_id = str(uuid4()), str(uuid4())
                paper = LibraryPaper(
                    id=paper_id,
                    library_id=library.id,
                    title=f"论文 {index}",
                    current_version_id=version_id if index != 2 else None,
                    archived=index == 1,
                )
                db.add(paper)
                db.flush()
                db.add(
                    PaperKnowledgeVersion(
                        id=version_id,
                        library_paper_id=paper_id,
                        source_kind="local_revision",
                        source_id=str(uuid4()),
                        source_paper_id=str(uuid4()),
                        project_id=str(uuid4()),
                        source_fingerprint="a" * 64,
                        snapshot_hash="b" * 64,
                        schema_version="paper-knowledge-1",
                        evidence_status="grounded",
                        content_json={},
                    )
                )
                expected.append({"id": paper_id, "version_id": version_id, "title": paper.title})
            db.add(
                KnowledgeCollectionMember(
                    collection_id=collection_id, library_paper_id=expected[0]["id"]
                )
            )

        base = f"/api/v1/knowledge/collections/{collection_id}/external-papers"
        paper_ids = ",".join(item["id"] for item in reversed(expected))
        response = api.get(base, params={"paper_ids": paper_ids})
        assert response.status_code == 200, response.text
        assert response.json() == {"items": list(reversed(expected[4:])), "has_more": True}
        narrow = api.get(base, params={"paper_ids": ",".join(row["id"] for row in expected[:5])})
        assert narrow.json() == {"items": expected[3:5], "has_more": False}
        assert (
            api.get(base, params={"paper_ids": ",".join(["x" * 36, expected[4]["id"]])}).status_code
            == 422
        )
        over_limit = ",".join([expected[3]["id"]] * 49)
        assert api.get(base, params={"paper_ids": over_limit}).status_code == 422

        with Session(engine) as db, db.begin():
            assert db.query(KnowledgeCollectionMember).count() == 1
            assert db.query(Job).count() == 0
            archive_target(db, "knowledge_collection", collection_id)
        archived = api.get(base, params={"paper_ids": expected[3]["id"]})
        assert archived.status_code == 404

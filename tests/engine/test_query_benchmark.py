"""Frozen P4 local recall benchmark: three synthetic paper types, 24 questions."""

import pytest
import test_knowledge
from researchgraph.knowledge_models import EvidenceSpan, KnowledgeNode, ModelRun
from researchgraph.knowledge_store import KnowledgeError, KnowledgeStore
from researchgraph.models import AttachmentRevision, Chunk, Paper, Project, now
from researchgraph.query_models import NoteUseGrant
from researchgraph.query_retrieval import retrieve
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_query_graph import production
from test_query_retrieval import notes

seeded = test_knowledge.seeded


@pytest.fixture
def benchmark(seeded):
    _, engine, eid = seeded
    production(engine, eid)
    with Session(engine) as session, session.begin():
        for key, title, text in [
            (
                "theory",
                "Synthetic theoretical convergence",
                "The convergence theorem assumes a convex objective and bounded gradients. "
                "Rate O(1/t). 非凸目标不在证明范围。",
            ),
            (
                "review",
                "Synthetic systematic review",
                "The systematic review searched 4 databases and included 32 studies. "
                "Heterogeneous protocols prevent pooled effect estimates. 检索范围为四个数据库。",
            ),
        ]:
            session.add(Paper(id=key, project_id="project", title=title, created_at=now()))
            session.flush()
            session.add(
                AttachmentRevision(
                    id=key + "-v",
                    paper_id=key,
                    sha256=("c" if key == "theory" else "d") * 64,
                    parser_version="synthetic-1",
                    page_count=1,
                    warnings=[],
                    created_at=now(),
                )
            )
            session.flush()
            session.add(
                Chunk(
                    id=key + "-c",
                    revision_id=key + "-v",
                    page_index=0,
                    page_label="1",
                    block_index=0,
                    text=text,
                    bbox=[0.0, 0.0, 100.0, 100.0],
                )
            )
            session.flush()
            KnowledgeStore(session).ensure_document(key + "-v")
    return engine, eid


POSITIVE = [
    ("accuracy 81%", "version"),
    ("3 agents", "version"),
    ("Prior work Smith", "version"),
    ("72%", "version"),
    ("Our method", "version"),
    ("合成样例", "version"),
    ("convergence theorem", "theory-v"),
    ("convex objective", "theory-v"),
    ("bounded gradients", "theory-v"),
    ("O(1/t)", "theory-v"),
    ("非凸目标", "theory-v"),
    ("systematic review", "review-v"),
    ("4 databases", "review-v"),
    ("32 studies", "review-v"),
    ("Heterogeneous protocols", "review-v"),
    ("四个数据库", "review-v"),
]


@pytest.mark.parametrize("question,expected", POSITIVE)
def test_gold_source_in_top_twenty(benchmark, question, expected):
    engine, _ = benchmark
    with Session(engine) as session, session.begin():
        result = retrieve(session, "project", question, [], limit=20)
        assert expected in {hit["data"].get("document_version_id") for hit in result["hits"]}


@pytest.mark.parametrize(
    "negative",
    [
        "absent",
        "other_project",
        "old_version",
        "mock",
        "rejected",
        "bad_quote",
        "personal_off",
        "revoked_note",
    ],
)
def test_gold_negative_refuses_or_returns_no_evidence(benchmark, tmp_path, negative):
    engine, eid = benchmark
    question, kinds, personal = "accuracy", ["knowledge"], False
    if negative in {"personal_off", "revoked_note"}:
        notes(engine, tmp_path)
        question, kinds = "Private synthetic", ["note"]
        if negative == "revoked_note":
            personal = True
            with Session(engine) as session, session.begin():
                session.add(
                    NoteUseGrant(root_id="root", allow_local=False, allow_model=False, revision=2)
                )
    with Session(engine) as session, session.begin():
        if negative == "absent":
            question = "unfindablequartzxyzz"
        elif negative == "other_project":
            session.add(Project(id="other", name="Other", description="", created_at=now()))
            session.flush()
            with pytest.raises(KnowledgeError, match="论文不属于"):
                retrieve(session, "other", question, ["paper"])
            return
        elif negative == "old_version":
            session.add(
                AttachmentRevision(
                    id="new-version",
                    paper_id="paper",
                    sha256="f" * 64,
                    parser_version="synthetic-2",
                    page_count=1,
                    warnings=[],
                    created_at="9999",
                )
            )
        elif negative == "mock":
            session.get(ModelRun, "run").provider = "mock"
        elif negative == "rejected":
            for node in session.scalars(select(KnowledgeNode)):
                node.review_status = "rejected"
        elif negative == "bad_quote":
            session.get(EvidenceSpan, eid).quote = "fabricated quotation"
        session.flush()
        result = retrieve(
            session, "project", question, [], source_kinds=kinds, include_personal=personal
        )
        assert not result["hits"] and result["status"] == "no_evidence"

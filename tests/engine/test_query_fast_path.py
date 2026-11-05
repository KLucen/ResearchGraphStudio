"""Independent adversarial checks for Query bulk validation and batched FTS updates."""

import copy

import pytest
import test_knowledge
from researchgraph import query_graph, query_retrieval
from researchgraph.graph_models import SourceAssertion
from researchgraph.knowledge_models import AuthorizedRoot, EvidenceSpan, NodeEvidence
from researchgraph.knowledge_store import KnowledgeError, KnowledgeStore
from researchgraph.models import AttachmentRevision, Chunk, Paper, Project, now
from researchgraph.query_graph import eligible_nodes, expand_graph
from researchgraph.query_retrieval import rebuild_index, retrieve
from researchgraph.reading_support import support_paths
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from test_query_graph import production, second_paper
from test_query_retrieval import notes, science_rows

seeded = test_knowledge.seeded


def test_prevalidated_endpoints_still_reject_an_extra_cross_version_link(seeded):
    _, engine, eid = seeded
    ids = production(engine, eid)
    second_paper(engine)
    with Session(engine) as session, session.begin():
        other = session.scalar(
            select(EvidenceSpan.id).where(EvidenceSpan.document_version_id == "version2")
        )
        session.add(NodeEvidence(node_id=ids["m"], evidence_id=other, role="support"))
    with Session(engine) as session:
        before = science_rows(session)
        candidates = {n.id for n in eligible_nodes(session, "project", ["paper"])}
        assert ids["m"] not in candidates
        graph = expand_graph(session, "project", ["paper"], [ids["c"]], [])
        assert ids["m"] not in {n["id"] for n in graph["nodes"]}
        assert all(edge["target_id"] != ids["m"] for edge in graph["associations"])
        assert science_rows(session) == before


@pytest.mark.parametrize(
    "bad", ["empty", "unknown", "quote", "bbox", "foreign", "direction", "project"]
)
def test_prevalidated_paths_revalidate_their_own_edge_evidence(seeded, bad):
    _, engine, eid = seeded
    ids = production(engine, eid)
    second_paper(engine)
    with Session(engine) as session, session.begin():
        edge = session.scalar(
            select(SourceAssertion).where(
                SourceAssertion.source_id == ids["c"], SourceAssertion.target_id == ids["m"]
            )
        )
        if bad == "empty":
            edge.evidence_ids = []
        elif bad == "unknown":
            edge.evidence_ids = ["missing-span"]
        elif bad in {"quote", "bbox"}:
            span = session.get(EvidenceSpan, eid)
            fields = {
                column.name: copy.deepcopy(getattr(span, column.name))
                for column in EvidenceSpan.__table__.columns
            }
            fields["id"] = "edge-span"
            fields["start_offset"] += 1
            fields["quote"] = span.quote[1:]
            fields["quote" if bad == "quote" else "bbox_list"] = (
                "changed quote" if bad == "quote" else [[50, 50, 100, 100]]
            )
            session.add(EvidenceSpan(**fields))
            edge.evidence_ids = ["edge-span"]
        elif bad == "foreign":
            edge.evidence_ids = [
                session.scalar(
                    select(EvidenceSpan.id).where(EvidenceSpan.document_version_id == "version2")
                )
            ]
        elif bad == "direction":
            edge.relation = "HAS_CONDITION"
        else:
            session.add(Project(id="other", name="other", description="", created_at=now()))
            session.flush()
            edge.project_id = "other"
    with Session(engine) as session:
        nodes = {n.id: n for n in eligible_nodes(session, "project", ["paper"])}
        assert set(ids.values()) == set(nodes)
        store = KnowledgeStore(session).reading()
        slow = support_paths(store, "version", nodes)
        fast = support_paths(store, "version", nodes, prevalidated=True)
        assert fast == slow and all(target != ids["m"] for _, target, _ in fast)
        graph = expand_graph(session, "project", ["paper"], [ids["c"]], [])
        assert ids["m"] not in {node["id"] for node in graph["nodes"]}
        assert len(graph["nodes"]) == 3
        before = science_rows(session)
        found = retrieve(
            session,
            "project",
            "accuracy",
            ["paper"],
            source_kinds=["knowledge"],
            knowledge_kinds=["claim"],
        )
        assert {n["id"] for n in found["graph"]["nodes"]} == {n["id"] for n in graph["nodes"]}
        assert science_rows(session) == before


def test_retrieve_validates_nodes_once_and_public_graph_still_revalidates(seeded, monkeypatch):
    _, engine, eid = seeded
    ids = production(engine, eid)
    calls = []
    original = eligible_nodes

    def tracked(session, project_id, paper_ids):
        calls.append((project_id, tuple(paper_ids)))
        return original(session, project_id, paper_ids)

    monkeypatch.setattr(query_graph, "eligible_nodes", tracked)
    monkeypatch.setattr(query_retrieval, "eligible_nodes", tracked)
    with Session(engine) as session, session.begin():
        before = science_rows(session)
        found = retrieve(session, "project", "accuracy", [])
        assert len(found["graph"]["nodes"]) == 4
        assert calls == [("project", ())]
        assert science_rows(session) == before
        expand_graph(session, "project", ["paper"], [ids["c"]], [])
        assert calls == [("project", ()), ("project", ("paper",))]


def test_retrieve_local_node_reuse_respects_scope_and_rejects_foreign_seed(seeded):
    _, engine, eid = seeded
    production(engine, eid)
    other = second_paper(engine)
    with Session(engine) as session, session.begin():
        before = science_rows(session)
        found = retrieve(session, "project", "accuracy", ["paper"])
        assert {n["paper_id"] for n in found["graph"]["nodes"]} == {"paper"}
        assert found["independent_sources"] == ["paper:version"]
        assert all(h["data"].get("paper_id") == "paper" for h in found["hits"])
        with pytest.raises(KnowledgeError, match="查询种子"):
            expand_graph(session, "project", ["paper"], [other["c"]], [])
        assert science_rows(session) == before


@pytest.mark.parametrize("change", ["quote", "foreign_link", "latest"])
def test_retrieve_revalidates_sources_on_next_call_in_same_session(seeded, change):
    _, engine, eid = seeded
    ids = production(engine, eid)
    second_paper(engine)
    with Session(engine) as session, session.begin():
        assert retrieve(session, "project", "accuracy", ["paper"])["graph"]["nodes"]
        if change == "quote":
            session.get(EvidenceSpan, eid).quote = "invalid source quote"
        elif change == "foreign_link":
            other = session.scalar(
                select(EvidenceSpan.id).where(EvidenceSpan.document_version_id == "version2")
            )
            session.add(NodeEvidence(node_id=ids["m"], evidence_id=other, role="support"))
        else:
            session.add(
                AttachmentRevision(
                    id="new-current-version",
                    paper_id="paper",
                    sha256="e" * 64,
                    parser_version="synthetic-new",
                    page_count=1,
                    warnings=[],
                    created_at=now(),
                )
            )
        session.flush()
        before = science_rows(session)
        found = retrieve(session, "project", "accuracy", ["paper"])
        assert ids["m"] not in {n["id"] for n in found["graph"]["nodes"]}
        if change != "foreign_link":
            assert not found["graph"]["nodes"]
        assert science_rows(session) == before


def test_retrieve_rechecks_note_authorization_without_session_cache(seeded, tmp_path):
    _, engine, eid = seeded
    production(engine, eid)
    notes(engine, tmp_path)
    with Session(engine) as session, session.begin():
        KnowledgeStore(session).query().set_note_grant("project", "root", True, True)
        before = science_rows(session)
        found = retrieve(session, "project", "Private", [], include_personal=True, purpose="model")
        assert {h["source_kind"] for h in found["hits"]} == {"note"}
        session.get(AuthorizedRoot, "root").active = False
        assert not retrieve(
            session, "project", "Private", [], include_personal=True, purpose="model"
        )["hits"]
        assert science_rows(session) == before


def test_retrieve_skips_unused_index_fingerprint_but_reindex_retains_it(seeded, monkeypatch):
    _, engine, _ = seeded
    fingerprints = []
    original = query_retrieval.digest

    def tracked(value):
        if isinstance(value, list):
            fingerprints.append(value)
        return original(value)

    monkeypatch.setattr(query_retrieval, "digest", tracked)
    with Session(engine) as session, session.begin():
        before = science_rows(session)
        retrieve(session, "project", "accuracy", [])
        assert fingerprints == []
        rebuilt = rebuild_index(session, "project")
        assert len(fingerprints) == 1 and len(rebuilt["fingerprint"]) == 64
        assert science_rows(session) == before


def scoped_raw_sources(engine):
    with Session(engine) as session, session.begin():
        session.add_all(
            [
                Paper(id="paper2", project_id="project", title="Second paper", created_at=now()),
                Paper(id="no-version", project_id="project", title="Unparsed", created_at=now()),
            ]
        )
        session.flush()
        session.add(
            AttachmentRevision(
                id="version2",
                paper_id="paper2",
                sha256="f" * 64,
                parser_version="synthetic",
                page_count=1,
                warnings=[],
                created_at=now(),
            )
        )
        session.flush()
        for index in range(6):
            session.add(
                Chunk(
                    id=f"scoped-primary-{index}",
                    revision_id="version",
                    page_index=0,
                    page_label="1",
                    block_index=index + 1,
                    text="needle primaryonly",
                    bbox=[0, 0, 100, 100],
                )
            )
        session.add(
            Chunk(
                id="scoped-secondary",
                revision_id="version2",
                page_index=0,
                page_label="1",
                block_index=0,
                text="needle plus many additional background words to lower the lexical rank",
                bbox=[0, 0, 100, 100],
            )
        )


@pytest.mark.parametrize("scope", ["papers", "versions"])
def test_explicit_multisource_scope_balances_matching_papers_before_limit(seeded, scope):
    _, engine, _ = seeded
    scoped_raw_sources(engine)
    with Session(engine) as session, session.begin():
        before = science_rows(session)
        ordinary = retrieve(session, "project", "needle", [], limit=4, source_kinds=["chunk"])
        assert {h["data"]["paper_id"] for h in ordinary["hits"]} == {"paper"}
        assert "scope_coverage" not in ordinary
        assert ordinary["ranking_policy"] == "lexical-graph-1"
        papers = ["paper", "paper2"] if scope == "papers" else []
        versions = None if scope == "papers" else ["version", "version2"]
        found = retrieve(
            session,
            "project",
            "needle",
            papers,
            version_ids=versions,
            limit=4,
            source_kinds=["chunk"],
        )
        assert len(found["hits"]) == 4
        assert {h["data"]["paper_id"] for h in found["hits"]} == {"paper", "paper2"}
        assert found["scope_coverage"] == {
            "requested_paper_ids": ["paper", "paper2"],
            "covered_paper_ids": ["paper", "paper2"],
            "missing_paper_ids": [],
        }
        assert found["ranking_policy"] == "lexical-graph-scoped-2"
        assert science_rows(session) == before


@pytest.mark.parametrize("case", ["limit", "no_match", "no_version", "metadata_only"])
def test_scoped_coverage_discloses_missing_without_fabricating_evidence(seeded, case):
    _, engine, _ = seeded
    scoped_raw_sources(engine)
    with Session(engine) as session, session.begin():
        session.get(Paper, "paper").title = "metadataonly"
        session.flush()
        before = science_rows(session)
        paper_ids = ["paper", "paper2"]
        question, limit, source_kinds = "needle", 4, ["chunk"]
        if case == "limit":
            limit = 1
        elif case == "no_match":
            question = "primaryonly"
        elif case == "no_version":
            paper_ids.append("no-version")
        else:
            paper_ids = ["paper"]
            question, source_kinds = "metadataonly", ["paper"]
        found = retrieve(
            session,
            "project",
            question,
            paper_ids,
            limit=limit,
            source_kinds=source_kinds,
        )
        coverage = found["scope_coverage"]
        assert coverage["requested_paper_ids"] == sorted(paper_ids)
        assert coverage["missing_paper_ids"] == [
            "no-version"
            if case == "no_version"
            else "paper"
            if case == "metadata_only"
            else "paper2"
        ]
        assert len(found["hits"]) <= limit
        assert all(h["source_kind"] in source_kinds for h in found["hits"])
        if case == "no_match":
            assert all(h["data"]["paper_id"] == "paper" for h in found["hits"])
        if case == "metadata_only":
            assert coverage["covered_paper_ids"] == [] and found["hits"]
        assert science_rows(session) == before


def test_batched_index_diff_crosses_parameter_batch_and_preserves_other_project(seeded):
    _, engine, _ = seeded
    with Session(engine) as session, session.begin():
        session.add_all(
            [
                Chunk(
                    id=f"bulk-{i}",
                    revision_id="version",
                    page_index=0,
                    page_label="1",
                    block_index=i + 10,
                    text=f"bulk synthetic {i}",
                    bbox=[0, 0, 100, 100],
                )
                for i in range(905)
            ]
        )
        session.add(Project(id="other", name="other", description="", created_at=now()))
    with Session(engine) as session, session.begin():
        science = science_rows(session)
        first = rebuild_index(session, "project")
        assert first["entries"] == 907  # Paper, existing raw paragraph, 905 new chunks.
        assert science_rows(session) == science
        target = session.execute(
            text("SELECT id FROM query_index_entries WHERE object_id='bulk-0'")
        ).scalar_one()
        session.execute(
            text("INSERT INTO query_fts VALUES (:id,'other','other private text','')"),
            {"id": target},
        )
        for index in range(905):
            session.get(Chunk, f"bulk-{index}").text = f"updated {index}"
    with Session(engine) as session, session.begin():
        science = science_rows(session)
        changed = rebuild_index(session, "project")
        assert changed["updated"] == 905
        assert rebuild_index(session, "project")["updated"] == 0
        assert session.execute(
            text("SELECT text FROM query_fts WHERE project_id='other'")
        ).scalars().all() == ["other private text"]
        assert (
            session.execute(
                text("SELECT count(*) FROM query_fts WHERE project_id='project'")
            ).scalar_one()
            == changed["entries"]
        )
        assert science_rows(session) == science


def test_rebuild_purges_orphan_personal_fts_after_revocation(seeded, tmp_path):
    _, engine, _ = seeded
    notes(engine, tmp_path)
    with Session(engine) as session, session.begin():
        rebuild_index(session, "project", include_personal=True)
        note_entry = session.execute(
            text("SELECT id FROM query_index_entries WHERE source_kind='note'")
        ).scalar_one()
        # Recoverable derived-index corruption must not retain revoked note bytes.
        session.execute(text("DELETE FROM query_index_entries WHERE id=:id"), {"id": note_entry})
        session.get(AuthorizedRoot, "root").active = False
    with Session(engine) as session, session.begin():
        rebuild_index(session, "project")
        assert (
            session.execute(
                text("SELECT count(*) FROM query_fts WHERE project_id='project' AND entry_id=:id"),
                {"id": note_entry},
            ).scalar_one()
            == 0
        )

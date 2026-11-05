"""Display filters use actual cited roots without rewriting historical source manifests."""

import copy

import test_knowledge
from researchgraph.query_models import QueryRun
from researchgraph.query_source_scope import paper_ids_from_sources, query_paper_ids
from sqlalchemy.orm import Session
from test_query_graph import production
from test_query_retrieval import second_paper
from test_query_save import prepared

seeded = test_knowledge.seeded


def test_nested_root_scope_is_explicit_project_scoped_and_never_guesses_note_owner():
    sources = [
        {"type": "passage", "roots": [{"paper_id": "b"}, {"document_version_id": "va"}]},
        {"type": "paper", "id": "a"},
        {"type": "node", "paper_id": "outside-project"},
        {"type": "note", "id": "private-note"},
    ]
    original = copy.deepcopy(sources)
    assert paper_ids_from_sources(sources, {"a", "b"}, {"va": "a"}) == ["a", "b"]
    assert sources == original
    assert paper_ids_from_sources([sources[-1]], {"a", "b"}) == []


def test_completed_history_uses_answer_citations_not_all_available_context(seeded):
    _, engine, eid = seeded
    production(engine, eid)
    second_paper(engine)
    prepared(engine)
    with Session(engine) as session:
        query = session.get(QueryRun, "query")
        original = copy.deepcopy((query.snapshot, query.request, query.input_hash))
        context_ids = {
            r.get("paper_id") for r in query.snapshot["context"]["references"] if r.get("paper_id")
        }
        assert len(context_ids) == 2
        assert query_paper_ids(session, query) == ["paper"]
        assert (query.snapshot, query.request, query.input_hash) == original
        assert not session.new and not session.dirty

"""Index representation changes preserve stored identities, bytes and source authority."""

import json

import pytest
import test_knowledge
from researchgraph.knowledge_store import stable_id
from researchgraph.models import Chunk
from researchgraph.query_retrieval import INDEX_POLICY, collect_entries, rebuild_index, strings
from researchgraph.unified_store import evidence_ids
from sqlalchemy import select, text
from sqlalchemy.orm import Session

seeded = test_knowledge.seeded


@pytest.mark.parametrize("object_id", ["原文:段落-α", "emoji:🧪", "path/with:colon"])
def test_reindex_preserves_existing_unicode_object_identity_and_bytes(seeded, object_id):
    _, engine, _ = seeded
    with Session(engine) as session, session.begin():
        session.add(
            Chunk(
                id=object_id,
                revision_id="version",
                page_index=0,
                page_label="1",
                block_index=1,
                text="Synthetic bilingual paragraph 原文 quoted exactly.",
                bbox=[0.0, 0.0, 100.0, 100.0],
            )
        )
        session.flush()
        source_before = [dict(row) for row in session.execute(select(Chunk.__table__)).mappings()]
        entry = next(
            row
            for row in collect_entries(session, "project")
            if row["source_kind"] == "chunk" and row["object_id"] == object_id
        )
        old_identifier = stable_id(INDEX_POLICY, f"project:chunk:{object_id}")
        assert entry["id"] == old_identifier
        stored = {**entry, "data": json.dumps(entry["data"], ensure_ascii=False, sort_keys=True)}
        session.execute(
            text(
                "INSERT INTO query_index_entries"
                "(id,project_id,source_kind,object_id,text,aliases,data) "
                "VALUES (:id,:project_id,:source_kind,:object_id,:text,:aliases,:data)"
            ),
            stored,
        )
        session.execute(
            text(
                "INSERT INTO query_fts(entry_id,project_id,text,aliases) "
                "VALUES (:id,:project_id,:text,:aliases)"
            ),
            stored,
        )
        rebuild_index(session, "project")
        actual = (
            session.execute(
                text("SELECT * FROM query_index_entries WHERE object_id=:oid"), {"oid": object_id}
            )
            .mappings()
            .one()
        )
        assert dict(actual) == stored
        assert (
            session.scalar(
                text("SELECT count(*) FROM query_fts WHERE entry_id=:id"), {"id": old_identifier}
            )
            == 1
        )
        assert [
            dict(row) for row in session.execute(select(Chunk.__table__)).mappings()
        ] == source_before


def test_nested_index_text_keeps_original_and_translation_order():
    payload = {
        "label": {"original": "first", "zh": "第一"},
        "aliases": ["second", {"extra": ["third", None, 42, True]}],
        "last": "fourth",
    }
    assert strings(payload) == ["first", "第一", "second", "third", "fourth"]


def test_evidence_scan_keeps_nested_source_ids_and_ignores_other_strings():
    payload = {
        "evidence_ids": ["top", "shared"],
        "nested": [{"evidence_ids": ["deep", "shared"]}, "not-an-evidence-id"],
    }
    assert evidence_ids(payload) == {"top", "shared", "deep"}


@pytest.mark.parametrize("invalid", [None, [[]]])
def test_invalid_evidence_lists_remain_rejected(invalid):
    with pytest.raises(TypeError):
        evidence_ids({"evidence_ids": invalid})

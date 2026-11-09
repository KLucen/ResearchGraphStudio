"""Focused Lite P0 usage and cache checks on isolated synthetic records."""

import pytest
from researchgraph.lite_usage import (
    cache_key,
    mark_cache_stale,
    read_cache,
    record_usage,
    write_cache,
)
from researchgraph.models import AttachmentRevision, Paper, Section, now
from sqlalchemy.orm import Session
from test_engine import client


def seed_source(session, project_id, suffix="1"):
    paper_id, version_id = f"paper-{suffix}", f"version-{suffix}"
    session.add(Paper(id=paper_id, project_id=project_id, title="Synthetic", created_at=now()))
    session.flush()
    session.add(
        AttachmentRevision(
            id=version_id,
            paper_id=paper_id,
            sha256="a" * 64,
            parser_version="synthetic-1",
            page_count=1,
            warnings=[],
            created_at=now(),
        )
    )
    session.flush()
    session.add(
        Section(
            id=f"section-{suffix}",
            document_version_id=version_id,
            title="Methods",
            ordinal=0,
            role="methods",
            parser="synthetic-1",
        )
    )
    session.flush()


def cache_parts(project_id):
    return dict(
        project_id=project_id,
        paper_id="paper-1",
        document_version_id="version-1",
        section_id="section-1",
        task_kind="A",
        input_fingerprint="b" * 64,
        prompt_version="A01-v1",
        schema_version="guide-1",
        provider="synthetic",
        model="synthetic",
        config_fingerprint="c" * 64,
        source_hash="a" * 64,
    )


def scope(parts):
    return {
        name: parts[name]
        for name in ("project_id", "paper_id", "document_version_id", "section_id", "task_kind")
    }


def test_lite_usage_zero_calls_is_explicit(tmp_path):
    with client(tmp_path) as api:
        project = api.post(
            "/api/v1/projects",
            json={"name": "Lite usage"},
            headers={"Idempotency-Key": "usage-zero"},
        ).json()
        response = api.get(f"/api/v1/projects/{project['id']}/lite/usage")
        assert response.status_code == 200, response.text
        assert response.json() == {
            "project_id": project["id"],
            "paper_id": None,
            "calls": 0,
            "retry_count": 0,
            "cache_hits": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "unknown_usage_calls": 0,
            "unrecorded_runs": 0,
            "unattributed_runs": 0,
            "calls_known": True,
            "estimated_usage_calls": 0,
            "cost_estimate": 0.0,
            "cost_known": True,
            "by_kind": [],
        }


def test_usage_rows_and_cache_are_additive(tmp_path):
    with client(tmp_path) as api:
        project = api.post(
            "/api/v1/projects",
            json={"name": "Lite usage rows"},
            headers={"Idempotency-Key": "usage-rows"},
        ).json()
        parts = cache_parts(project["id"])
        key = cache_key(parts)
        with Session(api.app.state.engine) as session, session.begin():
            seed_source(session, project["id"])
            record_usage(
                session,
                project_id=project["id"],
                paper_id="paper-1",
                document_version_id="version-1",
                task_kind="A",
                input_tokens=100,
                output_tokens=20,
                retry_count=1,
                usage_source="provider",
            )
            write_cache(session, cache_key_value=key, response={"state": "draft"}, **parts)
            assert read_cache(session, key, **scope(parts)) is not None
            assert mark_cache_stale(session, key, "source changed", **scope(parts))
        value = api.get(f"/api/v1/projects/{project['id']}/lite/usage").json()
        assert value["calls"] == 1
        assert value["retry_count"] == 1
        assert value["input_tokens"] == 100
        assert value["output_tokens"] == 20
        assert value["total_tokens"] == 120
        assert value["cost_known"] is False
        assert value["by_kind"][0]["task_kind"] == "A"


def test_retry_requests_are_recorded_as_separate_calls(tmp_path):
    """A failed request plus one retry must aggregate as two actual calls."""

    with client(tmp_path) as api:
        project = api.post(
            "/api/v1/projects",
            json={"name": "Lite retry rows"},
            headers={"Idempotency-Key": "usage-retry-rows"},
        ).json()
        with Session(api.app.state.engine) as session, session.begin():
            seed_source(session, project["id"])
            with pytest.raises(ValueError, match="initial request"):
                record_usage(
                    session,
                    project_id=project["id"],
                    paper_id="paper-1",
                    document_version_id="version-1",
                    task_kind="A",
                    retry_count=2,
                )
            record_usage(
                session,
                project_id=project["id"],
                paper_id="paper-1",
                document_version_id="version-1",
                task_kind="A",
                input_tokens=60,
                output_tokens=10,
                retry_count=0,
                usage_source="provider",
                status="failed",
            )
            record_usage(
                session,
                project_id=project["id"],
                paper_id="paper-1",
                document_version_id="version-1",
                task_kind="A",
                input_tokens=40,
                output_tokens=10,
                retry_count=1,
                usage_source="provider",
                status="succeeded",
            )
        value = api.get(f"/api/v1/projects/{project['id']}/lite/usage").json()
        assert value["calls"] == 2
        assert value["retry_count"] == 1
        assert value["input_tokens"] == 100
        assert value["output_tokens"] == 20
        assert value["total_tokens"] == 120


def test_unknown_usage_is_counted_once_and_cost_stays_unknown(tmp_path):
    with client(tmp_path) as api:
        project = api.post(
            "/api/v1/projects",
            json={"name": "Lite unknown usage"},
            headers={"Idempotency-Key": "usage-unknown"},
        ).json()
        with Session(api.app.state.engine) as session, session.begin():
            seed_source(session, project["id"])
            record_usage(
                session,
                project_id=project["id"],
                paper_id="paper-1",
                document_version_id="version-1",
                task_kind="paper_overview",
                usage_source="unknown",
            )
        value = api.get(f"/api/v1/projects/{project['id']}/lite/usage").json()
        assert value["calls"] == 1
        assert value["unknown_usage_calls"] == 1
        assert value["cost_known"] is False
        assert value["cost_estimate"] is None


def test_cache_hit_has_zero_new_calls_and_rejects_fabricated_usage(tmp_path):
    with client(tmp_path) as api:
        project = api.post(
            "/api/v1/projects",
            json={"name": "Lite cache hit"},
            headers={"Idempotency-Key": "usage-cache-hit"},
        ).json()
        with Session(api.app.state.engine) as session, session.begin():
            seed_source(session, project["id"])
            base = dict(
                project_id=project["id"],
                paper_id="paper-1",
                document_version_id="version-1",
                task_kind="A",
                cache_hit=True,
            )
            with pytest.raises(ValueError, match="cache hits cannot record token"):
                record_usage(session, input_tokens=10, **base)
            with pytest.raises(ValueError, match="cache hits cannot record cost"):
                record_usage(session, cost_estimate=1.0, **base)
            record_usage(session, **base)
        value = api.get(f"/api/v1/projects/{project['id']}/lite/usage").json()
        assert value["calls"] == 0
        assert value["cache_hits"] == 1
        assert value["input_tokens"] == value["output_tokens"] == value["total_tokens"] == 0
        assert value["cost_estimate"] == 0.0


def test_cache_validates_complete_identity_and_retains_old_response(tmp_path):
    with client(tmp_path) as api:
        project = api.post(
            "/api/v1/projects",
            json={"name": "Lite scoped cache"},
            headers={"Idempotency-Key": "usage-cache-scope"},
        ).json()
        parts = cache_parts(project["id"])
        key = cache_key(parts)
        with Session(api.app.state.engine) as session, session.begin():
            seed_source(session, project["id"])
            seed_source(session, project["id"], "2")
            original = write_cache(session, cache_key_value=key, response={"old": True}, **parts)
            assert read_cache(session, key, **scope(parts)) is original
            assert read_cache(session, key, **{**scope(parts), "paper_id": "paper-2"}) is None
            assert read_cache(session, key, **{**scope(parts), "section_id": None}) is None
            with pytest.raises(ValueError, match="immutable"):
                write_cache(session, cache_key_value=key, response={"new": True}, **parts)
            with pytest.raises(ValueError, match="supplied identity"):
                write_cache(
                    session, cache_key_value=key, response={}, **{**parts, "model": "other"}
                )
            with pytest.raises(ValueError, match="provider"):
                write_cache(
                    session,
                    cache_key_value=key,
                    response={},
                    **{**parts, "provider": None},
                )
            wrong_section = {**parts, "section_id": "section-2"}
            with pytest.raises(ValueError, match="section does not belong"):
                write_cache(
                    session, cache_key_value=cache_key(wrong_section), response={}, **wrong_section
                )
            assert original.response == {"old": True}
            for field in (name for name in parts if name != "section_id"):
                incomplete = {k: v for k, v in parts.items() if k != field}
                with pytest.raises(ValueError, match=field):
                    cache_key(incomplete)
                with pytest.raises(ValueError, match=field):
                    cache_key({**parts, field: ""})
            assert cache_key({**parts, "input_fingerprint": "d" * 64}) != key
            assert cache_key({**parts, "config_fingerprint": "d" * 64}) != key
            assert (
                read_cache(session, key, **{**scope(parts), "document_version_id": "version-2"})
                is None
            )
            wrong_source = {**parts, "source_hash": "d" * 64}
            with pytest.raises(ValueError, match="source hash"):
                write_cache(
                    session, cache_key_value=cache_key(wrong_source), response={}, **wrong_source
                )
            assert mark_cache_stale(session, key, "changed", **scope(parts))
            assert read_cache(session, key, **scope(parts)) is None
            assert read_cache(session, key, allow_stale=True, **scope(parts)).response == {
                "old": True
            }

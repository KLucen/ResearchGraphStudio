"""Publish an explicitly reviewed partial graph through isolated sidecar HTTP.

The default synthetic response has 19 nodes, 20 edges, and 11 invalid
type/direction combinations. The quote-mismatch case has 18 nodes and 18 edges
with exactly one unlocatable node quote. Each case runs without a model request.
"""

from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import os
import secrets
import sqlite3
import sys
import tempfile
import urllib.error
import urllib.request
from contextlib import closing
from pathlib import Path
from typing import Any
from unittest.mock import patch
from urllib.parse import urlsplit
from uuid import uuid4


def failed_response(source: dict[str, Any], *, quote_mismatch: bool) -> dict[str, Any]:
    """Create anonymous responses with isolated validation failures."""
    kinds = [
        "RESEARCH_QUESTION",
        *(["METHOD"] * 4),
        *(["CONCEPT"] * 5),
        *(["FINDING"] * 4),
        *(["CONTRIBUTION"] * 5),
    ]
    refs = [{"source_id": source["ref"], "quote": source["text"], "occurrence_index": 0}]
    valid = [
        ("INVESTIGATES", 1, 6),
        ("USES", 1, 2),
        ("ANALYZES", 2, 6),
        ("ANALYZES", 3, 7),
        ("YIELDS", 2, 11),
        ("YIELDS", 3, 12),
        ("CONTRIBUTES_TO", 11, 15),
        ("CONTRIBUTES_TO", 12, 16),
        ("RELATED_TO", 6, 15),
    ]
    invalid = [
        ("USES", 2, 6),
        ("USES", 3, 7),
        ("USES", 4, 8),
        ("ANALYZES", 1, 3),
        ("ANALYZES", 11, 7),
        ("YIELDS", 6, 11),
        ("YIELDS", 7, 12),
        ("CONTRIBUTES_TO", 2, 15),
        ("CONTRIBUTES_TO", 3, 16),
        ("INVESTIGATES", 6, 1),
        ("RELATED_TO", 1, 2),
    ]
    edge_specs = [*valid, *invalid]
    if quote_mismatch:
        kinds.pop()
        edge_specs = [
            *valid,
            ("INVESTIGATES", 1, 7),
            ("INVESTIGATES", 1, 8),
            ("INVESTIGATES", 1, 9),
            ("INVESTIGATES", 1, 10),
            ("USES", 1, 3),
            ("USES", 1, 4),
            ("ANALYZES", 4, 8),
            ("ANALYZES", 5, 9),
            ("YIELDS", 4, 13),
        ]
    return {
        "schema_version": "paper-knowledge-1",
        "paper_card": {
            "research_question": "合成研究问题",
            "motivation": "",
            "method_summary": "合成软件夹具，不是真实科学结论。",
            "contributions": [],
            "main_findings": [],
            "limitations": [],
        },
        "graph": {
            "nodes": [
                {
                    "id": f"n{index}",
                    "type": kind,
                    "label_zh": f"合成知识{index}",
                    "label_en": f"Synthetic {index}",
                    "description_zh": "仅供本机恢复软件回归的匿名知识。",
                    "basis": "EXPLICIT",
                    "source_refs": [
                        {
                            **refs[0],
                            "quote": "A missing quote attributed to the anonymous paper.",
                        }
                    ]
                    if quote_mismatch and index == 16
                    else copy.deepcopy(refs),
                }
                for index, kind in enumerate(kinds, 1)
            ],
            "edges": [
                {
                    "id": f"e{index}",
                    "source": f"n{left}",
                    "target": f"n{right}",
                    "type": kind,
                    "basis": "EXPLICIT",
                    "source_refs": copy.deepcopy(refs),
                }
                for index, (kind, left, right) in enumerate(edge_specs, 1)
            ],
        },
    }


def seed_failed_run(
    data_dir: Path, provider_url: str, model: str, *, quote_mismatch: bool
) -> tuple[str, str, str]:
    """Seed only the temporary database after the target engine created its schema."""
    from researchgraph.import_plan_models import ImportSession
    from researchgraph.knowledge_extraction_models import KnowledgeExtractionRun
    from researchgraph.knowledge_library import ensure_library
    from researchgraph.knowledge_sources import build_knowledge_sources
    from researchgraph.knowledge_tasks import queue_knowledge_extract
    from researchgraph.model_document_models import LlmDocumentParse, LlmDocumentSegment
    from researchgraph.models import Paper, Project, now
    from researchgraph.paper_knowledge import PREVIOUS_PROMPT_VERSION, knowledge_contract
    from researchgraph.storage import make_engine
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    engine = make_engine(data_dir)
    project_id, paper_id, import_id, parse_id = (str(uuid4()) for _ in range(4))
    try:
        with Session(engine) as db, db.begin():
            db.add(
                Project(id=project_id, name="Anonymous recovery", description="", created_at=now())
            )
            db.flush()
            db.add(
                Paper(
                    id=paper_id,
                    project_id=project_id,
                    title="Anonymous recovery paper",
                    created_at=now(),
                )
            )
            db.flush()
            db.add(
                ImportSession(
                    id=import_id,
                    project_id=project_id,
                    source_kind="pdf",
                    selection_id="synthetic",
                    source_snapshot={"paper_id": paper_id},
                    plan={},
                    status="succeeded",
                    created_at=now(),
                    updated_at=now(),
                )
            )
            db.flush()
            db.add(
                LlmDocumentParse(
                    id=parse_id,
                    import_session_id=import_id,
                    parse_version="llm-document-1",
                    status="succeeded",
                    modality="text",
                    warnings=[],
                    created_at=now(),
                    updated_at=now(),
                )
            )
            db.flush()
            db.add(
                LlmDocumentSegment(
                    id=str(uuid4()),
                    parse_id=parse_id,
                    chapter_ref="c0",
                    chapter_title="1 Synthetic Methods",
                    chapter_level=1,
                    chapter_order=0,
                    kind="paragraph",
                    ordinal=0,
                    text="Anonymous software fixture describes a synthetic method and its limits.",
                    locator={"page": 1},
                    status="ok",
                    warnings=[],
                    created_at=now(),
                )
            )
            db.flush()
            library = ensure_library(db)
            library.settings_json = {
                **library.settings_json,
                "allow_network": True,
                "auto_connect": True,
            }
            with patch(
                "researchgraph.knowledge_tasks.knowledge_contract",
                return_value=knowledge_contract(PREVIOUS_PROMPT_VERSION),
            ):
                job = queue_knowledge_extract(
                    db,
                    paper_id=paper_id,
                    source_kind="model_parse",
                    source_version_id=parse_id,
                    model_snapshot={
                        "provider": "local",
                        "model": model,
                        "base_url": provider_url,
                        "parameters": {"timeout_seconds": 5},
                    },
                    allow_network=True,
                    auto_connect=True,
                )
            manifest = build_knowledge_sources(db, paper_id, "model_parse", parse_id)
            run = db.scalar(
                select(KnowledgeExtractionRun).where(KnowledgeExtractionRun.job_id == job.id)
            )
            assert run is not None and run.library_paper_id is not None
            run.raw_response = json.dumps(
                failed_response(manifest["sources"][0], quote_mismatch=quote_mismatch),
                ensure_ascii=False,
            )
            run.status, run.error_code, run.request_sent = (
                "failed",
                "KNOWLEDGE_QUOTE_MISMATCH"
                if quote_mismatch
                else "KNOWLEDGE_RESPONSE_SCHEMA_INVALID",
                True,
            )
            run.usage_json = {
                "calls": 1,
                "input_tokens": None,
                "output_tokens": None,
                "total_tokens": None,
                "usage_source": "unknown",
                "cost": None,
            }
            run.request_metadata = {**run.request_metadata, "response_complete": True}
            job.status, job.stage, job.error = "failed", "failed", run.error_code
            return job.id, run.id, run.library_paper_id
    finally:
        engine.dispose()


def read_state(database: Path, job_id: str) -> dict[str, Any]:
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as db:
        db.execute("PRAGMA query_only=ON")
        db.row_factory = sqlite3.Row
        run = dict(
            db.execute(
                "SELECT status,error_code,request_sent,raw_response,usage_json,output_json,"
                "version_id FROM knowledge_extraction_runs WHERE job_id=?",
                (job_id,),
            ).fetchone()
        )
        job = dict(
            db.execute(
                "SELECT status,stage,error,payload FROM jobs WHERE id=?", (job_id,)
            ).fetchone()
        )
        counts = {
            table: db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in (
                "paper_knowledge_versions",
                "knowledge_analysis_events",
                "knowledge_connection_runs",
                "knowledge_connection_requests",
            )
        }
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert not db.execute("PRAGMA foreign_key_check").fetchall()
    return {"failed_run": run, "failed_job": job, "counts": counts}


def run(
    executable: Path | None, source_python: Path | None, *, quote_mismatch: bool = False
) -> dict[str, Any]:
    if (executable is None) == (source_python is None):
        raise ValueError("Choose one packaged executable or source Python")
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "services/engine"))
    spec = importlib.util.spec_from_file_location(
        "local_recovery_smoke_harness", Path(__file__).with_name("smoke-knowledge-library.py")
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Knowledge smoke harness is missing")
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    shared = helper.harness()

    class NoRequestProvider(shared.SyntheticProvider):
        def _handler(self) -> Any:
            parent = super()._handler()
            fixture = self

            class Handler(parent):
                def do_GET(self) -> None:
                    fixture.metadata_requests += 1
                    self.send_body(500, b"{}", "application/json")

                def do_POST(self) -> None:
                    self.rfile.read(int(self.headers.get("Content-Length", "0")))
                    fixture.calls.append("unexpected")
                    self.send_body(500, b"{}", "application/json")

            return Handler

    env = {
        name: os.environ[name]
        for name in (
            "SYSTEMROOT",
            "WINDIR",
            "TEMP",
            "TMP",
            "USERPROFILE",
            "LOCALAPPDATA",
            "APPDATA",
        )
        if name in os.environ
    }
    env["PATH"] = str(Path(os.environ.get("SYSTEMROOT", "C:/Windows")) / "System32")
    if source_python:
        env["PYTHONPATH"] = str(root / "services/engine")
        command = [str(source_python.resolve()), "-m", "researchgraph", "--data-dir"]
    else:
        assert executable is not None
        command = [str(executable.resolve()), "--data-dir"]
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    token = secrets.token_urlsafe(48)

    def request(
        base: str, method: str, path: str, body: Any = None, *, key: str | None = None
    ) -> Any:
        assert urlsplit(base).hostname == "127.0.0.1"
        payload = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(base + path, data=payload, method=method)
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("Content-Type", "application/json")
        req.add_header("Idempotency-Key", key or secrets.token_hex(12))
        with opener.open(req, timeout=20) as response:
            return json.loads(response.read())

    with (
        tempfile.TemporaryDirectory(prefix="rgs-knowledge-local-recovery-") as folder,
        NoRequestProvider() as provider,
    ):
        isolated = Path(folder)
        data_dir = isolated / "data"
        database = data_dir / "researchgraph-lite.sqlite3"
        with helper.sidecar(command, isolated, token, env) as base:
            health = request(base, "GET", "/health")
            assert health["schema_version"] == "lite0020"
        job_id, run_id, paper_id = seed_failed_run(
            data_dir, provider.base_url, shared.MODEL, quote_mismatch=quote_mismatch
        )
        before = read_state(database, job_id)
        assert all(value == 0 for value in before["counts"].values())
        path = f"/knowledge/runs/{run_id}/local-recovery"
        replay_key = "anonymous-local-recovery-replay"
        original_nodes, original_edges, kept_nodes, kept_edges = (
            (18, 18, 17, 17) if quote_mismatch else (19, 20, 19, 9)
        )
        with helper.sidecar(command, isolated, token, env) as base:
            preview = request(base, "GET", path)
            assert preview["available"] and preview["published_version_id"] is None
            assert [
                preview[name]
                for name in ("original_nodes", "original_edges", "kept_nodes", "kept_edges")
            ] == [original_nodes, original_edges, kept_nodes, kept_edges]
            assert len(preview["excluded_edges"]) == original_edges - kept_edges
            if quote_mismatch:
                assert len(preview["excluded_nodes"]) == 1
                assert preview["excluded_nodes"][0]["reason"]
                assert preview["excluded_edges"][0]["reason"]
                assert "A missing quote attributed to the anonymous paper." not in json.dumps(
                    preview
                )
            else:
                assert all(
                    edge["code"] == "invalid_relation_types" and edge["reason"]
                    for edge in preview["excluded_edges"]
                )
            assert request(base, "GET", path) == preview
            assert read_state(database, job_id) == before  # Reading is not publication.
            try:
                request(base, "POST", path, {"preview_fingerprint": "0" * 64})
            except urllib.error.HTTPError as error:
                assert error.code == 409
                assert json.loads(error.read())["error"]["code"] == "KNOWLEDGE_LOCAL_RECOVERY_STALE"
            else:
                raise AssertionError("An unreviewed fingerprint was accepted")
            assert read_state(database, job_id) == before
            body = {"preview_fingerprint": preview["preview_fingerprint"]}
            result = request(base, "POST", path, body, key=replay_key)
            assert result["status"] == "partial" and result["library_paper_id"] == paper_id
            version_id = result["version_id"]
            assert request(base, "POST", path, body, key=replay_key) == result
            published = request(base, "GET", path)
            assert not published["available"] and published["published_version_id"] == version_id
            version = request(base, "GET", f"/knowledge/versions/{version_id}")
            content = version["content"]
            assert content["coverage"]["status"] == "partial"
            assert len(content["graph"]["nodes"]) == kept_nodes + 1
            assert len(content["graph"]["edges"]) == kept_edges + kept_nodes
            if quote_mismatch:
                assert not any(content["paper_card"].values())
            paper = request(base, "GET", f"/knowledge/papers/{paper_id}")
            assert paper["current_version"]["id"] == version_id and len(paper["versions"]) == 1
            assert request(base, "GET", "/jobs/" + job_id)["status"] == "failed"
            assert request(base, "GET", "/knowledge/runs")["items"][0]["status"] == "failed"
        with helper.sidecar(command, isolated, token, env) as base:
            assert request(base, "GET", path) == published
            assert request(base, "POST", path, body, key=replay_key) == result
            assert request(base, "GET", f"/knowledge/versions/{version_id}") == version
            assert request(base, "GET", "/jobs/" + job_id)["status"] == "failed"
        after = read_state(database, job_id)
        assert after["failed_run"] == before["failed_run"]
        assert after["failed_job"] == before["failed_job"]
        assert after["counts"] == {**before["counts"], "paper_knowledge_versions": 1}
        assert not provider.calls and provider.metadata_requests == 0 and not provider.errors
        return {
            "status": "passed",
            "target": "source" if source_python else "packaged",
            "schema_version": health["schema_version"],
            "case": "legacy_quote_mismatch" if quote_mismatch else "legacy_relation_types",
            "original_nodes": original_nodes,
            "original_edges": original_edges,
            "retained_nodes": kept_nodes,
            "retained_edges": kept_edges,
            "isolated_nodes": original_nodes - kept_nodes,
            "isolated_edges": original_edges - kept_edges,
            "published_status": "partial",
            "published_versions": 1,
            "original_failed_raw_usage_preserved": True,
            "unreviewed_fingerprint_rejected": True,
            "get_and_restart_idempotency": True,
            "automatic_analysis_events": 0,
            "provider_requests": 0,
            "model_requests": 0,
            "restart_extra_requests": 0,
            "real_model_calls": 0,
            "non_loopback_requests": 0,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--executable", type=Path)
    target.add_argument("--source-python", type=Path)
    parser.add_argument("--quote-mismatch", action="store_true")
    args = parser.parse_args()
    report = run(args.executable, args.source_python, quote_mismatch=args.quote_mismatch)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

"""Exercise new reading cards over real loopback HTTP, without real model traffic.

The temporary database contains an invented PDF and explicitly seeded historical
overview/model-parse fixtures. Seeding happens only while its sidecar is stopped.
The library snapshot remains independent of both new card generations.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import secrets
import sqlite3
import tempfile
import time
from contextlib import closing
from pathlib import Path
from typing import Any
from uuid import uuid4


def harness() -> Any:
    spec = importlib.util.spec_from_file_location(
        "card_smoke_shared", Path(__file__).with_name("smoke-knowledge-library.py")
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Synthetic sidecar harness is missing")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def seed_anonymous_history(database: Path, project: str, paper: str, revision: str) -> str:
    """Only populate our freshly created temporary database, with no live process."""
    session_id, parse_id = str(uuid4()), str(uuid4())
    timestamp = "2026-01-01T00:00:00Z"
    legacy = {
        "schema_version": "paper_overview_graph.v1",
        "paper_card": {
            "research_question": "Synthetic reading question",
            "motivation": "Invented regression fixture",
            "method_summary": "Synthetic shared memory method",
            "contributions": [],
            "main_findings": [],
            "limitations": ["Not a real scientific paper"],
        },
        "graph": {
            "nodes": [
                {
                    "id": "n1",
                    "type": "CONCEPT",
                    "label_zh": "Synthetic shared memory",
                    "label_en": "shared memory",
                    "description_zh": "An invented concept for software tests.",
                    "basis": "EXPLICIT",
                }
            ],
            "edges": [],
        },
    }
    with closing(sqlite3.connect(database)) as db, db:
        assert db.execute("SELECT count(*) FROM papers").fetchone()[0] == 1
        digest = db.execute(
            "SELECT sha256 FROM attachment_revisions WHERE id=?", (revision,)
        ).fetchone()[0]
        db.execute(
            "INSERT INTO paper_overview_results "
            "(id,project_id,paper_id,document_version_id,pdf_hash,input_hash,cache_key,"
            "schema_version,prompt_version,provider_id,model_id,paper_card_json,graph_json,"
            "status,graph_status,request_metadata,cache_hit,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                str(uuid4()),
                project,
                paper,
                revision,
                digest,
                "a" * 64,
                "b" * 64,
                legacy["schema_version"],
                "historical-synthetic",
                "synthetic",
                "synthetic",
                json.dumps(legacy["paper_card"]),
                json.dumps(legacy["graph"]),
                "COMPLETED",
                "READY",
                "{}",
                0,
                timestamp,
                timestamp,
            ),
        )
        db.execute(
            "INSERT INTO import_sessions "
            "(id,project_id,source_kind,selection_id,source_snapshot,plan,status,"
            "created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (
                session_id,
                project,
                "pdf",
                "synthetic-model-fixture",
                json.dumps({"paper_id": paper}),
                "{}",
                "succeeded",
                timestamp,
                timestamp,
            ),
        )
        db.execute(
            "INSERT INTO llm_document_parses "
            "(id,import_session_id,parse_version,modality,status,warnings,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (parse_id, session_id, "synthetic-1", "text", "succeeded", "[]", timestamp, timestamp),
        )
        db.execute(
            "INSERT INTO llm_document_segments "
            "(id,parse_id,chapter_ref,chapter_title,chapter_level,chapter_order,kind,ordinal,"
            "text,status,warnings,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                str(uuid4()),
                parse_id,
                "chapter-methods",
                "Methods",
                1,
                0,
                "paragraph",
                0,
                "We propose a shared memory method for a synthetic study.",
                "ok",
                "[]",
                timestamp,
            ),
        )
        db.execute(
            "INSERT INTO llm_document_outputs "
            "(id,import_session_id,parse_id,item_kind,status,output_json,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (
                str(uuid4()),
                session_id,
                parse_id,
                "paper_overview",
                "succeeded",
                json.dumps(legacy),
                timestamp,
                timestamp,
            ),
        )
    return parse_id


def run(executable: Path | None, source_python: Path | None) -> dict[str, Any]:
    if (executable is None) == (source_python is None):
        raise ValueError("Choose one packaged executable or source Python")
    support = harness()
    shared = support.harness()

    class CardProvider(shared.SyntheticProvider):
        reject_next_model_excerpt = False

        def respond(self, body: dict[str, Any]) -> tuple[dict[str, Any], str]:
            assert body.get("model") == shared.MODEL and body.get("stream") is True
            assert body.get("stream_options", {}).get("include_usage") is True
            assert not body.get("tools")
            wrapper = json.loads(body["messages"][1]["content"])
            context, schema = wrapper["untrusted_source_data"], wrapper["output_schema"]
            original = "We propose a shared memory method for a synthetic study."
            translation = "我们提出一种用于合成研究的共享记忆方法。"
            model_source = context["source_kind"] == "model_parse"
            if model_source:
                excerpt = next(
                    excerpt
                    for source in context["sources"]
                    for excerpt in source["excerpts"]
                    if excerpt["text"] == original
                )
                evidence = {"excerpt_id": excerpt["excerpt_id"], "translation_zh": translation}
            else:
                assert schema["title"] == "PaperCardSetDraft"
                source = next(s for s in context["sources"] if original in s["text"])
                evidence = {
                    "source_id": source["source_id"],
                    "quote_en": original,
                    "occurrence_index": 0,
                    "translation_zh": translation,
                }
            cards = []
            for number, kind, title in (
                (1, "architecture_algorithm", "合成共享记忆方法"),
                (2, "key_concept", "共享记忆"),
            ):
                cards.append(
                    {
                        "id": f"c{number}",
                        "kind": kind,
                        "attribution": "AUTHOR",
                        "title_zh": title,
                        "title_en": "shared memory",
                        "body_zh": "匿名合成材料介绍共享记忆方法，不声明真实科学发现。",
                        "reading_guide_zh": "查看所引原文及可用位置，不补造实验结论。",
                        "evidence": [dict(evidence)],
                    }
                )
            if model_source and self.reject_next_model_excerpt:
                self.reject_next_model_excerpt = False
                cards[1]["evidence"][0]["excerpt_id"] = "q9999999"
            return {
                "schema_version": "paper-card-set-2",
                "article_overview_zh": "这份合成材料介绍共享记忆方法。",
                "overview_card_ids": ["c1", "c2"],
                "card_set_intro_zh": "包含方法与关键概念卡，可逐条回看原文。",
                "coverage_notes": ["软件夹具不包含真实实验结果或作者自述局限。"],
                "cards": cards,
            }, context["source_kind"]

    root = Path(__file__).resolve().parents[1]
    env = {
        key: os.environ[key]
        for key in ("SYSTEMROOT", "WINDIR", "TEMP", "TMP", "USERPROFILE", "LOCALAPPDATA", "APPDATA")
        if key in os.environ
    }
    env["PATH"] = str(Path(os.environ.get("SYSTEMROOT", "C:/Windows")) / "System32")
    env["PYTHONUTF8"], env["PYTHONIOENCODING"] = "1", "utf-8"
    if source_python:
        env["PYTHONPATH"] = str(root / "services" / "engine")
        command = [str(source_python), "-m", "researchgraph", "--data-dir"]
    else:
        command = [str(executable), "--data-dir"]
    token = secrets.token_urlsafe(48)
    request = shared.request
    with (
        tempfile.TemporaryDirectory(prefix="rgs-paper-card-set-smoke-") as folder,
        CardProvider() as provider,
    ):
        isolated = Path(folder)
        pdf = isolated / "anonymous-source.pdf"
        pdf_hash = shared.make_pdf(pdf)
        database = isolated / "data" / "researchgraph-lite.sqlite3"
        with support.sidecar(command, isolated, token, env) as base:
            assert request(base, token, "GET", "/health")["schema_version"] == "lite0020"
            project = request(base, token, "POST", "/projects", {"name": "Anonymous card smoke"})
            connection = request(
                base,
                token,
                "POST",
                "/settings/connections",
                {"name": "Loopback cards", "provider": "local", "base_url": provider.base_url},
            )
            profile = request(
                base,
                token,
                "POST",
                "/settings/models",
                {
                    "name": "Synthetic cards",
                    "connection_id": connection["id"],
                    "model": shared.MODEL,
                    "parameters": {"timeout_seconds": 20},
                },
            )
            request(base, token, "POST", "/settings/model-roles", {"extraction": profile["id"]})
            imported = request(
                base,
                token,
                "POST",
                f"/projects/{project['id']}/papers/import/pdf",
                {"path": str(pdf), "mode": "reference"},
            )
            job = shared.wait_job(base, token, imported["id"])
            paper, revision = job["result"]["paper_id"], job["result"]["revision_id"]
            local_get = f"/papers/{paper}/overview?document_version_id={revision}"
            assert request(base, token, "GET", local_get) is None
            assert provider.calls == []
        parse = seed_anonymous_history(database, project["id"], paper, revision)
        model_get = f"/papers/{paper}/model-overview?parse_id={parse}"

        def verify_cards(view: dict[str, Any], kind: str) -> None:
            assert view["status"] == "COMPLETED", view
            assert view["paper_card"] is None and view["graph"] is None
            content = view["card_set"]
            assert content["schema_version"] == "paper-card-set-2"
            assert content["source_kind"] == kind and content["semantic_accuracy"] == "unverified"
            assert len(content["cards"]) == 2 and len(content["overview_card_ids"]) == 2
            for card in content["cards"]:
                assert card["id"] not in {"c1", "c2"}
                evidence = card["evidence"][0]
                assert evidence["translation_status"] == "auxiliary"
                position = evidence["position"]
                assert position["chapter_ref"]
                if kind == "local_revision":
                    assert position["page_start"] == position["page_end"] == 1
                else:
                    assert position["page_start"] is None and position["page_end"] is None
                    assert position["segment_id"]

        with support.sidecar(command, isolated, token, env) as base:
            # Neither old overview is visible or automatically regenerated.
            assert request(base, token, "GET", local_get) is None
            assert request(base, token, "GET", model_get) is None
            assert provider.calls == []
            library_paper = request(
                base,
                token,
                "POST",
                "/knowledge/papers/collect",
                {"paper_id": paper, "source_kind": "local_revision", "source_id": revision},
            )
            library_id = library_paper["id"]
            before_library = request(base, token, "GET", f"/knowledge/papers/{library_id}")
            assert before_library["current_version"]["content"]["graph"]["nodes"]
            for name, source, get_path, kind in (
                ("overview", revision, local_get, "local_revision"),
                ("model-overview", parse, model_get, "model_parse"),
            ):
                queued = request(
                    base,
                    token,
                    "POST",
                    f"/papers/{paper}/{name}/generate",
                    {"document_version_id": source, "allow_network": True},
                )
                shared.wait_job(base, token, queued["job_id"])
                view = request(base, token, "GET", get_path)
                verify_cards(view, kind)
                repeated = request(
                    base,
                    token,
                    "POST",
                    f"/papers/{paper}/{name}/generate",
                    {"document_version_id": source, "allow_network": True},
                )
                assert repeated["id"] == view["id"] and repeated["status"] == "COMPLETED"
            local = request(base, token, "GET", local_get)
            assert provider.calls == ["local_revision", "model_parse"] and not provider.errors
            assert request(base, token, "GET", f"/knowledge/papers/{library_id}") == before_library
            assert request(base, token, "GET", "/knowledge/reports")["items"] == []
            with closing(sqlite3.connect(database)) as db:
                assert db.execute("SELECT count(*) FROM paper_graph_layouts").fetchone()[0] == 0
                assert (
                    db.execute("SELECT count(*) FROM model_overview_graph_layouts").fetchone()[0]
                    == 0
                )
                assert (
                    db.execute("SELECT count(*) FROM paper_knowledge_versions").fetchone()[0] == 1
                )

            provider.reject_next_model_excerpt = True
            queued = request(
                base,
                token,
                "POST",
                f"/papers/{paper}/model-overview/generate",
                {"document_version_id": parse, "allow_network": True, "force_regenerate": True},
            )
            job_path = f"/jobs/{queued['job_id']}"
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                failed_job = request(base, token, "GET", job_path)
                if failed_job["status"] not in {"queued", "running"}:
                    break
                time.sleep(0.1)
            else:
                raise AssertionError("Synthetic card failure did not finish within 45 seconds")
            assert failed_job["status"] == "failed"
            assert failed_job["reading_task"] == "paper_card_set"
            preview = request(base, token, "GET", model_get)
            assert preview["status"] == "FAILED" and preview["local_recovery_available"] is True
            assert preview["recovery_summary"] == {
                "original_cards": 2,
                "retained_cards": 1,
                "excluded_cards": 1,
                "invalid_evidence": 1,
            }
            recovery_path = f"/papers/{paper}/model-document-outputs/{preview['id']}/local-recovery"
            recovered = request(base, token, "POST", recovery_path, {})
            assert recovered["status"] == "partial"
            model = request(base, token, "GET", model_get)
            assert model["status"] == "PARTIAL" and len(model["card_set"]["cards"]) == 1
            assert model["card_set"]["cards"][0]["title_zh"] == "合成共享记忆方法"
            assert request(base, token, "GET", job_path) == failed_job
            assert provider.calls == ["local_revision", "model_parse", "model_parse"]

        with support.sidecar(command, isolated, token, env) as base:
            assert request(base, token, "GET", local_get)["card_set"] == local["card_set"]
            assert request(base, token, "GET", model_get) == model
            assert request(base, token, "POST", recovery_path, {}) == recovered
            assert request(base, token, "GET", job_path) == failed_job
            assert request(base, token, "GET", f"/knowledge/papers/{library_id}") == before_library
            assert provider.calls == ["local_revision", "model_parse", "model_parse"]
            assert not provider.errors
        assert hashlib.sha256(pdf.read_bytes()).hexdigest() == pdf_hash
        return {
            "status": "passed",
            "sidecar": "packaged" if executable else "source",
            "schema_version": "lite0020",
            "card_schema": "paper-card-set-2",
            "real_model_calls": 0,
            "non_loopback_requests": 0,
            "synthetic_local_card_requests": 1,
            "synthetic_model_card_requests": 2,
            "synthetic_total_tokens": 192,
            "get_cache_restart_extra_requests": 0,
            "local_recovery_extra_requests": 0,
            "local_recovery_retained_cards": 1,
            "local_recovery_excluded_cards": 1,
            "failed_job_preserved": True,
            "old_overview_fallback": False,
            "library_graph_unchanged": True,
            "graph_layout_writes": 0,
            "anonymous_pdf_unchanged": True,
            "scientific_quality_validated": False,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--executable", type=Path)
    target.add_argument("--source-python", type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.executable, args.source_python), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

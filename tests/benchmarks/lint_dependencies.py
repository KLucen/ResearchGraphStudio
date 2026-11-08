"""Offline fixed-scale Lint/dependency benchmark on a brand-new synthetic database.

Use the same script for before/after, selecting an immutable runtime source tree
with --source-root. The output directory must not exist. The harness never opens
or upgrades an existing user database and does not call a model/provider.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import math
import os
import platform
import sqlite3
import statistics
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CANDIDATES = 10_000
CHUNKS = 20_000
EXPECTED_TARGETS = 30_011
BATCH_SIZE = 100
QUERY_REPEATS = 12


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_fingerprint(package: Path) -> dict[str, str]:
    return {
        path.relative_to(package).as_posix(): sha256(path)
        for path in sorted(package.rglob("*"))
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix not in {".pyc", ".pyo"}
    }


def percentiles(samples: list[dict[str, Any]]) -> dict[str, Any]:
    values = sorted(row["wall_seconds"] for row in samples)
    return {
        "samples": len(values),
        "p50_seconds": statistics.median(values),
        "p95_seconds": values[max(0, math.ceil(len(values) * 0.95) - 1)],
        "max_seconds": max(values),
        "sum_seconds": sum(values),
        "sql_statements": sum(row["sql_statements"] for row in samples),
        "p95_policy": "nearest-rank ceil(0.95*n), no interpolation",
    }


def benchmark(output: Path, source_root: Path) -> dict[str, Any]:
    # CLI checks this boundary before importing any application/test modules.
    package = source_root / "researchgraph"
    before = source_fingerprint(package)
    sys.path[:0] = [str(source_root), str(ROOT / "tests/engine")]
    import researchgraph
    import test_knowledge
    from researchgraph.knowledge_models import KnowledgeNode, ModelRun, NodeEvidence
    from researchgraph.knowledge_store import KnowledgeStore, text_hash
    from researchgraph.lint_contracts import LintRequest
    from researchgraph.lint_models import DependencyIndex, LintIssue, LintRun
    from researchgraph.lint_service import LintStore, dependencies
    from researchgraph.models import Chunk
    from researchgraph.reading_models import CandidateMetadata
    from researchgraph.storage import SCHEMA_HEAD
    from researchgraph.wiki_store import WikiMutations
    from sqlalchemy import event, func, insert, select, text
    from sqlalchemy.orm import Session
    from test_query_graph import production

    if Path(researchgraph.__file__).resolve().parent != package:
        raise RuntimeError("Loaded runtime does not match --source-root")
    spec = importlib.util.spec_from_file_location(
        "query_benchmark_memory", ROOT / "tests/benchmarks/query_retrieval.py"
    )
    assert spec and spec.loader
    memory_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(memory_module)
    memory_usage = memory_module.memory_usage
    report: dict[str, Any] = {
        "benchmark": "lint-dependencies-fixed-1",
        "started_at_utc": datetime.now(UTC).isoformat(),
        "source_root": str(source_root),
        "source_sha256": before,
        "harness_sha256": sha256(Path(__file__).resolve()),
        "fixture_sha256": {
            name: sha256(ROOT / name)
            for name in (
                "tests/engine/test_knowledge.py",
                "tests/engine/test_query_graph.py",
                "tests/engine/test_reading_extraction.py",
                "tests/engine/test_engine.py",
                "tests/benchmarks/query_retrieval.py",
            )
        },
        "machine": {
            "platform": platform.platform(),
            "processor": platform.processor(),
            "cpu_count": os.cpu_count(),
            "python": sys.version,
            "python_executable": sys.executable,
            "sqlite": sqlite3.sqlite_version,
        },
        "application_schema": SCHEMA_HEAD,
        "distribution": {
            "candidates": CANDIDATES,
            "chunks": CHUNKS,
            "wiki_drafts": 2,
            "expected_lint_targets": EXPECTED_TARGETS,
            "batch_size": BATCH_SIZE,
            "description": (
                "Four tiny synthetic production-labelled fixture candidates plus 9,996 "
                "independent candidates sharing one validated evidence span; one fixture "
                "chunk plus 19,999 unique raw-only chunks. Two single-passage Wiki drafts "
                "cite paragraph and benchmark-chunk-00001 respectively. Matches the "
                "2026-11-05 fixed-scale benchmark distribution."
            ),
        },
        "isolation": {
            "fresh_database": True,
            "background_worker": False,
            "real_model_calls": 0,
            "production_database_writes": 0,
            "note": "Synthetic fixture only; start_worker=False; no provider invocation.",
        },
        "memory_initial": memory_usage(),
        "stages": [],
        "batch_samples": [],
        "queries": {},
        "limitations": (
            "One complete scan per runtime. This synthetic distribution and local "
            "machine measurement do not establish a general SLA or scientific accuracy. "
            "Peak RSS is an OS process-lifetime high-water mark including fixture seeding."
        ),
    }
    sql_count = 0
    sql_verbs: dict[str, int] = {}
    fixture = None
    engine = None
    event_stream = (output / "events.jsonl").open("x", encoding="utf-8")

    def emit(value: dict[str, Any]) -> None:
        encoded = json.dumps(value, ensure_ascii=False, default=str)
        event_stream.write(encoded + "\n")
        event_stream.flush()
        print(encoded, flush=True)

    def sql_event(_connection, _cursor, statement, _parameters, _context, _many):
        nonlocal sql_count
        sql_count += 1
        verb = statement.lstrip().split(None, 1)[0].upper() if statement.strip() else "EMPTY"
        sql_verbs[verb] = sql_verbs.get(verb, 0) + 1

    def measure(name: str, action: Callable[[], Any]) -> tuple[Any, dict[str, Any]]:
        initial_sql, initial_verbs = sql_count, dict(sql_verbs)
        started = time.perf_counter()
        result = action()
        sample = {
            "name": name,
            "wall_seconds": time.perf_counter() - started,
            "sql_statements": sql_count - initial_sql,
            "sql_verbs": {
                key: count - initial_verbs.get(key, 0)
                for key, count in sql_verbs.items()
                if count != initial_verbs.get(key, 0)
            },
            "memory": memory_usage(),
        }
        return result, sample

    def mutate(action: Callable[[Any], Any]) -> Any:
        with Session(engine) as session, session.begin():
            return action(session)

    def read_closure(kind: str, oid: str, direction: str) -> dict[str, Any]:
        # Traverse every result page, retaining the engine's complete closure semantics.
        items, pages, page_number, expected_total = [], [], 1, None
        with Session(engine) as session:
            while True:
                result = dependencies(
                    session,
                    "project",
                    object_type=kind,
                    object_id=oid,
                    direction=direction,
                    page=page_number,
                    page_size=100,
                )
                expected_total = result["total"] if expected_total is None else expected_total
                assert result["total"] == expected_total, "Closure changed during read"
                pages.append({key: value for key, value in result.items() if key != "items"})
                items.extend(result["items"])
                if len(items) >= expected_total:
                    break
                assert result["items"], "Closure pagination made no progress"
                page_number += 1
        assert len(items) == expected_total
        assert len({row["id"] for row in items}) == len(items)
        return {"items": items, "pages": pages, "total": expected_total}

    try:
        tick = time.perf_counter()
        data = output / "data"
        data.mkdir()
        fixture = test_knowledge.seeded.__wrapped__(data)
        _, engine, evidence_id = next(fixture)
        event.listen(engine, "before_cursor_execute", sql_event)
        production(engine, evidence_id)
        wiki_pages = []
        with Session(engine) as session, session.begin():
            template = session.scalar(select(KnowledgeNode).where(KnowledgeNode.kind == "claim"))
            original = {
                column.name: copy.deepcopy(getattr(template, column.name))
                for column in KnowledgeNode.__table__.columns
            }
            nodes, metadata, links = [], [], []
            for index in range(CANDIDATES - 4):
                row = copy.deepcopy(original)
                row.update(id=f"benchmark-node-{index:05d}", fingerprint=f"{index:064x}")
                row["payload"]["local_ref"] = f"benchmark-{index:05d}"
                row["text"] = f"Benchmark candidate {index} memory evidence"
                nodes.append(row)
                metadata.append(
                    {
                        "node_id": row["id"],
                        "quality": {},
                        "validation_status": "valid",
                        "canonical_id": None,
                        "policy_version": "benchmark-1",
                    }
                )
                links.append({"node_id": row["id"], "evidence_id": evidence_id, "role": "supports"})
            session.execute(insert(KnowledgeNode), nodes)
            session.execute(insert(CandidateMetadata), metadata)
            session.execute(insert(NodeEvidence), links)
            session.execute(
                insert(Chunk),
                [
                    {
                        "id": f"benchmark-chunk-{index:05d}",
                        "revision_id": "version",
                        "page_index": 0,
                        "page_label": "1",
                        "block_index": index + 1,
                        "text": (
                            f"Synthetic benchmark paragraph {index} context retrieval "
                            f"tokenmark{index:05d}."
                        ),
                        "bbox": [0.0, 0.0, 100.0, 100.0],
                    }
                    for index in range(CHUNKS - 1)
                ],
            )
            for index, chunk_id in enumerate(("paragraph", "benchmark-chunk-00001")):
                chunk = session.get(Chunk, chunk_id)
                wiki_pages.append(
                    WikiMutations(KnowledgeStore(session)).create_draft(
                        "project",
                        {
                            "title": f"Synthetic benchmark page {index}",
                            "passages": [
                                {
                                    "heading": "Source",
                                    "text": "Bounded interpretation.",
                                    "attribution": "model_synthesis",
                                    "dependencies": [
                                        {
                                            "type": "chunk",
                                            "id": chunk_id,
                                            "sha256": text_hash(chunk.text),
                                            "start": 0,
                                            "end": len(chunk.text),
                                            "quote": chunk.text,
                                        }
                                    ],
                                    "caveats": [],
                                    "conditions": [],
                                    "links": [],
                                }
                            ],
                        },
                        f"benchmark-wiki-page-{index}",
                    )
                )
        with Session(engine) as session:
            assert session.scalar(select(func.count()).select_from(KnowledgeNode)) == CANDIDATES
            assert session.scalar(select(func.count()).select_from(Chunk)) == CHUNKS
            model_runs_before = session.scalar(select(func.count()).select_from(ModelRun))
            report["database_schema"] = session.scalar(
                text("SELECT version_num FROM alembic_version")
            )
        report["seed_seconds"] = time.perf_counter() - tick
        report["memory_seeded"] = memory_usage()
        emit(
            {
                "event": "seeded",
                "seconds": report["seed_seconds"],
                "memory": report["memory_seeded"],
            }
        )

        run, sample = measure(
            "scan_prepare",
            lambda: mutate(
                lambda session: LintStore(KnowledgeStore(session)).start(
                    "project", LintRequest(), "benchmark-lint-start"
                )
            ),
        )
        sample["run"] = copy.deepcopy(run)
        report["stages"].append(sample)
        report["targets"] = run["total"]
        assert run["total"] == EXPECTED_TARGETS
        emit({"event": "prepared", **sample})
        tick = time.perf_counter()
        iteration = 0
        while run["status"] in {"queued", "running"}:
            iteration += 1
            assert iteration <= EXPECTED_TARGETS // BATCH_SIZE + 10, "Scan stopped advancing"
            run_id = run["id"]
            previous = {key: run.get(key) for key in ("processed", "phase", "status", "progress")}
            run, sample = measure(
                "scan_advance",
                lambda step_run_id=run_id, step_iteration=iteration: mutate(
                    lambda session: LintStore(KnowledgeStore(session)).advance(
                        "project", step_run_id, BATCH_SIZE, f"benchmark-step-{step_iteration}"
                    )
                ),
            )
            sample.update(iteration=iteration, previous=previous, run=copy.deepcopy(run))
            report["batch_samples"].append(sample)
            emit({"event": "batch", **sample})
        report["scan_advance_seconds"] = time.perf_counter() - tick
        report["batch_summary"] = percentiles(report["batch_samples"])
        report["initial_scan"] = run
        assert run["status"] == "completed"
        assert run["processed"] == EXPECTED_TARGETS
        assert not run["errors"]
        assert {key: run["counts"].get(key, 0) for key in ("error", "warning", "info")} == {
            "error": 0,
            "warning": 0,
            "info": 1,
        }
        with Session(engine) as session:
            issue_codes = list(
                session.scalars(select(LintIssue.code).where(LintIssue.run_id == run["id"]))
            )
            target_types: dict[str, int] = {}
            for target in session.get(LintRun, run["id"]).targets:
                target_types[target["type"]] = target_types.get(target["type"], 0) + 1
        report["initial_issue_codes"] = issue_codes
        report["target_distribution"] = target_types
        assert issue_codes == ["SOURCE_UNCHECKED"]

        first, sample = measure(
            "dependency_rebuild",
            lambda: mutate(
                lambda session: LintStore(KnowledgeStore(session)).rebuild_dependencies(
                    "project", "benchmark-index-first"
                )
            ),
        )
        sample["result"] = first
        report["stages"].append(sample)
        emit({"event": "rebuilt", **sample})

        def change_source(session):
            session.get(Chunk, "benchmark-chunk-00001").text = "Explicit synthetic source change."

        _, sample = measure("single_chunk_change", lambda: mutate(change_source))
        report["stages"].append(sample)
        second, sample = measure(
            "dependency_reconcile",
            lambda: mutate(
                lambda session: LintStore(KnowledgeStore(session)).rebuild_dependencies(
                    "project", "benchmark-index-changed"
                )
            ),
        )
        sample["result"] = second
        report["stages"].append(sample)
        emit({"event": "reconciled", **sample})
        assert any(
            row["object_type"] == "chunk"
            and row["object_id"] == "benchmark-chunk-00001"
            and row["change"] == "changed"
            for row in second["changes"]
        )

        for label, kind, oid, direction in (
            ("reverse_impact", "chunk", "benchmark-chunk-00001", "dependents"),
            ("forward_dependencies", "document", wiki_pages[1]["page_id"], "dependencies"),
        ):
            samples, expected_ids = [], None
            for iteration in range(QUERY_REPEATS):
                closure, sample = measure(
                    label,
                    lambda kind=kind, oid=oid, direction=direction: read_closure(
                        kind, oid, direction
                    ),
                )
                ids = sorted(row["id"] for row in closure["items"])
                expected_ids = ids if expected_ids is None else expected_ids
                assert ids == expected_ids
                sample.update(
                    iteration=iteration + 1, total=closure["total"], pages=len(closure["pages"])
                )
                samples.append(sample)
            report["queries"][label] = {
                "object_type": kind,
                "object_id": oid,
                "direction": direction,
                "summary": percentiles(samples),
                "samples": samples,
                "closure": closure,
            }
            if label == "reverse_impact":
                affected = {
                    object_type: len(
                        {
                            row["dependent_id"]
                            for row in closure["items"]
                            if row["dependent_type"] == object_type
                        }
                    )
                    for object_type in ("passage", "document")
                }
                assert affected == {"passage": 1, "document": 1}
                report["affected"] = affected
            else:
                assert any(
                    row["source_type"] == "chunk" and row["source_id"] == "benchmark-chunk-00001"
                    for row in closure["items"]
                )
            emit({"event": label, "summary": percentiles(samples), "total": closure["total"]})

        with Session(engine) as session:
            assert session.scalar(select(func.count()).select_from(ModelRun)) == model_runs_before
            report["dependency_edge_count"] = session.scalar(
                select(func.count()).select_from(DependencyIndex)
            )
        report["memory_final"] = memory_usage()
        report["database_files"] = {
            path.name: path.stat().st_size for path in data.glob("researchgraph.sqlite3*")
        }
        report["sql_total"] = {"statements": sql_count, "verbs": sql_verbs}
        report["passed"] = True
    except BaseException as error:
        report["passed"] = False
        report["failure"] = {"type": type(error).__name__, "message": str(error)}
        raise
    finally:
        if fixture is not None:
            try:
                next(fixture)
            except StopIteration:
                pass
        report["source_sha256_after"] = source_fingerprint(package)
        report["source_fingerprint_unchanged"] = report["source_sha256_after"] == before
        if not report["source_fingerprint_unchanged"]:
            report["passed"] = False
        report["memory_end"] = memory_usage()
        report["finished_at_utc"] = datetime.now(UTC).isoformat()
        (output / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8"
        )
        emit(
            {
                "event": "finished",
                "passed": report.get("passed", False),
                "report": str(output / "report.json"),
            }
        )
        event_stream.close()
    assert report["source_fingerprint_unchanged"], "Runtime source changed during benchmark"
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="Brand-new output directory")
    parser.add_argument(
        "--source-root",
        type=Path,
        default=ROOT / "services/engine",
        help="Directory containing the researchgraph package",
    )
    arguments = parser.parse_args()
    output = arguments.output.absolute()
    source_root = arguments.source_root.resolve()
    if output.exists() or output.is_symlink():
        parser.error("--output must be a new directory; existing data is never opened or removed")
    if not (source_root / "researchgraph/__init__.py").is_file():
        parser.error("--source-root must contain the researchgraph package")
    if output.is_relative_to(source_root):
        parser.error("--output must be outside --source-root")
    output.mkdir(parents=True, exist_ok=False)
    benchmark(output, source_root)


if __name__ == "__main__":
    main()

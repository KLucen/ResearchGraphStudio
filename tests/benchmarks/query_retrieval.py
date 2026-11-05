"""Reproducible offline Query benchmark on a brand-new synthetic database.

Run from the repository with the researchgraph-studio Conda interpreter::

    python tests/benchmarks/query_retrieval.py \
        --data-dir .local/query-benchmark-new --report .local/query-benchmark-new.json

The data directory MUST NOT exist. Existing databases are never opened, cleared
or migrated by this harness. It makes no model or external network calls. The
stress distribution is deliberately stated in the report; these measurements
do not establish accuracy or general workload performance.
"""

from __future__ import annotations

import argparse
import copy
import ctypes
import json
import math
import platform
import statistics
import sys
import time
from pathlib import Path
from typing import Any

NODE_COUNT = 10_000
CHUNK_COUNT = 20_000
WARM_QUESTIONS = ["tokenmark17000", "accuracy", "unfindablequartz", "tokenmark10000"] * 3


def memory_usage() -> dict[str, Any]:
    """OS resident-set high-water mark, not Python allocation/tracemalloc totals."""
    if sys.platform == "win32":
        from ctypes import wintypes

        class ProcessMemoryCounters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
                ("PrivateUsage", ctypes.c_size_t),
            ]

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        psapi.GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(ProcessMemoryCounters),
            wintypes.DWORD,
        ]
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        counters = ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        if not psapi.GetProcessMemoryInfo(
            kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        return {
            "peak_rss_bytes": counters.PeakWorkingSetSize,
            "current_rss_bytes": counters.WorkingSetSize,
            "source": "Windows GetProcessMemoryInfo.PeakWorkingSetSize",
        }
    import resource

    maximum = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return {
        "peak_rss_bytes": int(maximum if sys.platform == "darwin" else maximum * 1024),
        "current_rss_bytes": None,
        "source": "resource.getrusage(RUSAGE_SELF).ru_maxrss",
    }


def fts_storage(session: Any) -> dict[str, Any]:
    """Physical SQLite pages for all FTS5 shadow tables, measured with dbstat."""
    from sqlalchemy import text
    from sqlalchemy.exc import OperationalError

    logical_bytes = int(
        session.scalar(
            text(
                "SELECT COALESCE(SUM(LENGTH(CAST(text AS BLOB)) + "
                "LENGTH(CAST(aliases AS BLOB))),0) FROM query_fts"
            )
        )
    )
    logical = {
        "logical_text_utf8_bytes": logical_bytes,
        "logical_policy": "SUM UTF-8 bytes of text and aliases; excludes IDs/index/page overhead",
    }
    try:
        rows = (
            session.execute(
                text(
                    "SELECT name,SUM(pgsize) AS bytes FROM dbstat "
                    "WHERE name='query_fts' OR name GLOB 'query_fts_*' GROUP BY name ORDER BY name"
                )
            )
            .mappings()
            .all()
        )
    except OperationalError as error:
        if "no such table: dbstat" not in str(error.orig):
            raise
        # The Windows Conda SQLite build may omit ENABLE_DBSTAT_VTAB. A
        # database-size difference or payload length is not a physical-page
        # measurement; report the missing capability without inventing bytes.
        return {
            **logical,
            "bytes": None,
            "tables": None,
            "status": "unsupported",
            "source": "SQLite dbstat",
            "reason": "SQLite build does not provide dbstat (ENABLE_DBSTAT_VTAB)",
        }
    return {
        **logical,
        "bytes": sum(int(row["bytes"]) for row in rows),
        "tables": {row["name"]: int(row["bytes"]) for row in rows},
        "status": "measured",
        "source": "SQLite dbstat SUM(pgsize), including FTS5 shadow tables",
    }


def run_benchmark(data_dir: Path) -> dict[str, Any]:
    # Imports are deferred until the new-directory boundary has been checked.
    root = Path(__file__).resolve().parents[2]
    sys.path[:0] = [str(root / "services/engine"), str(root / "tests/engine")]
    import test_knowledge
    from researchgraph.knowledge_models import KnowledgeNode, NodeEvidence
    from researchgraph.models import Chunk
    from researchgraph.query_retrieval import retrieve
    from researchgraph.reading_models import CandidateMetadata
    from sqlalchemy import insert, select, text
    from sqlalchemy.orm import Session
    from test_query_graph import production

    baseline_memory = memory_usage()
    fixture = test_knowledge.seeded.__wrapped__(data_dir)
    started = time.perf_counter()
    try:
        _, engine, evidence_id = next(fixture)
        production(engine, evidence_id)
        with Session(engine) as session, session.begin():
            template = session.scalar(select(KnowledgeNode).where(KnowledgeNode.kind == "claim"))
            original = {
                column.name: copy.deepcopy(getattr(template, column.name))
                for column in KnowledgeNode.__table__.columns
            }
            nodes, metadata, links = [], [], []
            # Four genuine tiny fixture nodes + 9,996 independent candidates.
            for index in range(NODE_COUNT - 4):
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
                    for index in range(CHUNK_COUNT - 1)
                ],
            )
        seeding_seconds = time.perf_counter() - started
        del nodes, metadata, links, original
        memory_after_seed = memory_usage()
        samples = []
        # Cold includes the complete initially-empty derived index construction.
        for index, question in enumerate(["tokenmark00001", *WARM_QUESTIONS]):
            with Session(engine) as session, session.begin():
                tick = time.perf_counter()
                result = retrieve(session, "project", question, [])
                sample = {
                    "phase": "cold" if index == 0 else "warm",
                    "question": question,
                    "seconds": round(time.perf_counter() - tick, 6),
                    "hits": len(result["hits"]),
                    "graph_nodes": len(result["graph"]["nodes"]),
                }
            samples.append(sample)
            print(json.dumps(sample), flush=True)
        warm = sorted(sample["seconds"] for sample in samples[1:])
        with Session(engine) as session:
            scale = {
                name: session.scalar(text(f"SELECT COUNT(*) FROM {name}"))
                for name in ("knowledge_nodes", "chunks", "query_index_entries", "query_fts")
            }
            fts = fts_storage(session)
        if scale["knowledge_nodes"] != NODE_COUNT or scale["chunks"] != CHUNK_COUNT:
            raise RuntimeError("Synthetic scale is inconsistent; benchmark rejected")
        return {
            "benchmark": "query-retrieval-synthetic-1",
            "machine": platform.platform(),
            "python": sys.version.split()[0],
            "scale": scale,
            "seeding_seconds": round(seeding_seconds, 6),
            "cold_rebuild_and_query_seconds": samples[0]["seconds"],
            "warm_samples": len(warm),
            "warm_p50_seconds": statistics.median(warm),
            "warm_p95_seconds": warm[math.ceil(0.95 * len(warm)) - 1],
            "percentile_policy": "nearest-rank; n=12 gives p95=max",
            "samples": samples,
            "database_bytes": (data_dir / "researchgraph.sqlite3").stat().st_size,
            "fts_bytes": fts["bytes"],
            "fts_logical_text_utf8_bytes": fts["logical_text_utf8_bytes"],
            "fts_storage": fts,
            "peak_rss_bytes": memory_usage()["peak_rss_bytes"],
            "memory": {
                "baseline": baseline_memory,
                "after_seed": memory_after_seed,
                "final": memory_usage(),
                "policy": "OS process high-water mark including imports, seeding and retrieval",
            },
            "distribution": (
                "9,996 independent candidate Claims share one validated source span; "
                "four fixture nodes retain three legal support edges; 19,999 distinct raw-only "
                "paragraphs plus one original paragraph. Warm workload includes raw, knowledge/"
                "support and missing hits. No table, multi-paper or real-model quality claim."
            ),
            "model_calls": 0,
        }
    finally:
        fixture.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    data_dir, report_path = args.data_dir.resolve(), args.report.resolve()
    if data_dir.exists():
        parser.error("--data-dir must be a new, nonexistent directory; existing data is not opened")
    if report_path.exists() or report_path == data_dir:
        parser.error("--report must be a new output file; existing files are never overwritten")
    data_dir.mkdir(parents=True, exist_ok=False)
    report = run_benchmark(data_dir)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"report": str(report_path), "model_calls": 0}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

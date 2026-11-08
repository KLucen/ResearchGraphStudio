# Offline benchmarks

Run with the `researchgraph-studio` Conda interpreter from the repository root.
These scripts create synthetic data only and refuse existing output/data directories.

```powershell
conda run -n researchgraph-studio python tests/benchmarks/lint_dependencies.py --output .local/lint-benchmark-new
```

`lint_dependencies.py` uses 10,000 candidates, 20,000 chunks, two Wiki drafts,
and batches of 100. Its expected 30,011 Lint targets are checked against the
actual persisted distribution. `--source-root <directory>` selects a runtime
tree containing `researchgraph`, so the same harness can compare frozen sources.
Use a different fresh `--output` directory for every execution.

The report and JSONL event log retain preparation, every advance (including a
separate dependency phase when provided by the runtime), explicit index rebuild,
single-chunk reconciliation, and 12 complete forward/reverse closure reads.
They include wall times, SQL statement counts, OS current/peak RSS, source
fingerprints, Python/SQLite/schema and machine details. SQL counts include
commit-time flushes and count an executemany call as one executed statement;
transaction begin/commit protocol messages are not counted as SQL statements.
The initial scan must complete with one `SOURCE_UNCHECKED` info and no warnings,
errors, or failed rules; the changed chunk must affect one passage and one
document. Background workers and real model calls are absent.

The peak RSS is the OS process-lifetime high-water mark, including setup and
seeding; it is not a Python allocation count. Query P50/P95 use 12 sequential
samples with nearest-rank P95. One full scan per runtime on this distribution
does not establish a general SLA or scientific accuracy. Keep before and after
runs serial, and wait for the compared runtime sources to be frozen.

`query_retrieval.py` is the separate fixed-scale Query benchmark; consult its
module docstring for its `--data-dir` and `--report` arguments.

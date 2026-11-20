# ADR 0055: Save Post-processing Jobs Before Linking Import Plan Items

- Status: Accepted
- Date: 2026-11-19 (Asia/Shanghai)
- Extends: [ADR0054](0054-document-publication-integrity-recovery.md)

## Context

The publication-only recovery introduced by ADR0054 preserved validated model batches but did not correct the database write-order defect. The latest bounded diagnostic, read from the user database using SQLite `mode=ro` and `PRAGMA query_only=ON`, records `SQLITE_CONSTRAINT_FOREIGNKEY` (787). The task has exhausted its two publication recoveries (job attempt 6); all three extraction and both boundary checkpoints remain validated. SQLite `quick_check` is `ok` and `foreign_key_check` reports no violations. These checks describe a healthy committed database; they do not rule out a foreign-key error in a transaction that was rolled back.

An isolated reproduction with foreign-key enforcement enabled consistently fails when `_queue_selected_postprocessing()` adds a new `Job`, assigns that new ID to `ImportPlanItem.job_id`, and then triggers autoflush. With no ORM relationship ordering those operations, the plan-item `UPDATE` can precede the job `INSERT`. The selected overview therefore causes the final publication transaction to fail even though every model checkpoint is valid.

The previous batch test fixture used a bare SQLAlchemy `create_engine()` without enabling SQLite foreign keys. That fixture allowed this invalid ordering and missed the production defect. Its earlier passing results remain historical evidence of the narrower fixture, not proof of foreign-key-safe publication.

## Decision

1. Flush the new downstream `Job` in the existing publication transaction before assigning its ID to the plan item. Do not disable or defer foreign-key enforcement. Keep publication, segments, plan links, and downstream queue creation atomic; a later failure still rolls back the whole publication transaction.
2. Use the production `storage.make_engine()` in batch integration tests, with foreign-key enforcement explicitly asserted. Seed parent and child records in valid order. Cover ordinary publication and checkpoint-only recovery with selected overview/reading/translation jobs, including idempotent queue creation.
3. Retain the normal maximum of two explicit publication recoveries. Add one narrow compatibility exception for an older failed task only when the count is an integer equal to 2, no `publication_recovery_version` field exists, and the safe diagnostics exactly identify SQLite 787 / `SQLITE_CONSTRAINT_FOREIGNKEY` / `foreign_key` with phase `publication_failed`.
4. Preserve all existing qualification checks: exact task/session/run and plan-item ownership, frozen ranges, all expected validated extraction/boundary checkpoints, no successful parse, and source PDF stat-version revalidation before and inside publication. No SHA-256 content hash becomes a parsing prerequisite.
5. The explicit retry transaction records cumulative count 3, `publication_recovery_version=foreign-key-order-1`, and `publication_recovery_only=true`. It does not reset old attempts, failure history, batch results, request receipts, or usage. Both retry API entry points apply the same authorization.
6. The worker treats the persisted publication-only flag as binding. If the quota, source, or checkpoint conditions no longer match, it fails before initializing a provider or sending any model request; it must not fall back to ordinary batch parsing. The corrected third attempt does not authorize a fourth attempt after failure, interruption, or cancellation.
7. Task history and the paper panel distinguish local publication from model retries. The strict boolean recovery flag controls the publication button; exhausted recovery keeps checkpoints and hides the ineffective model-retry button. Selected overview or reading work may run afterward under its original plan and can incur separate model cost.

No schema migration is required; the Alembic head remains `lite0013`. The production user database is not modified as a development experiment, and the implementation does not automatically retry the user's failed task.

## Consequences

The now-recorded diagnostic and isolated reproduction identify a concrete local write-order defect, rather than an extraction or model-response failure. A compatible old task can explicitly publish its saved results after installing the fix, without uploading the PDF or repeating extraction/boundary requests. A successful publication can still enqueue the originally selected downstream generation.

Tests with production foreign-key enforcement replace the earlier incomplete fixture for this behavior. They establish transaction and recovery correctness on synthetic data; they do not establish real-provider compatibility or the scientific accuracy of extracted text, formulas, tables, or cross-page merging. Actual verification and package status are recorded in the [verification report](../document-fk-order-verification-20261119.md).

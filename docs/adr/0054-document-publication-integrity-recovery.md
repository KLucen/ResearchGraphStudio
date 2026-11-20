# ADR 0054: Recover Batched Document Publication After Integrity Failure

- Status: Accepted
- Date: 2026-11-18

## Context

A model-first PDF task can finish every extraction batch and boundary review, then fail while atomically publishing the assembled parse and segments. Earlier failure handling retained only the exception class, so a task history entry such as `IntegrityError` did not identify a database constraint. The final transaction rolls back while committed batch checkpoints remain available.

The 2026-11-18 affected task had three of three extraction batches and two of two boundary checkpoints validated, with eight requests already accounted for. Its final publication failed. A read-only health check reported SQLite `quick_check = ok` and no foreign-key violations. The old record did not contain the SQLite error code/name, so the violated constraint cannot be reconstructed after the fact.

## Decision

1. Record bounded integrity diagnostics for future publication failures: database dialect, recognized SQLite error code/name, and a fixed constraint category. Never persist the driver message, SQL, parameters, file paths, or model material.
2. Add a publication-only recovery path. It is available only when the exact task/session/run relationship matches, every expected extraction and boundary checkpoint is validated, each range matches the frozen plan, and no successful parse already exists.
3. Before publishing, revalidate every stored batch result and the source PDF's existing stat-based version fields. Repeat task, checkpoint, source, and successful-parse checks inside the final write transaction. This continues the existing no-content-hash prerequisite policy.
4. Do not initialize a provider, render/re-upload the PDF, or dispatch extraction/boundary requests during publication-only recovery. Limit explicit publication recovery to two attempts per task.
5. After parse publication, keep the import plan's selected post-processing behavior. A selected overview or reading task may start separately and can make its own model request; the UI states this before the user retries.

No schema migration is required. Failed parse history remains preserved; a recovered parse is appended as a successful version.

## Consequences

The installed build that created the failed task did not advertise publication-only recovery. After installing a build containing this ADR, its preserved validated checkpoints can be explicitly republished if the source metadata and database state still match; the missing historical SQLite detail does not block that bounded recovery. Its already-sent requests are not repeated. Any selected downstream generation remains separately billable.

Recovery proves database publication and checkpoint consistency, not the scientific correctness of model-extracted text, formulae, or tables.

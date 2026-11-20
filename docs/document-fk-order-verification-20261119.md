# Document Publication Foreign-key Order: Verification

Date: 2026-11-19 (Asia/Shanghai)

## Finding and Read-only Diagnostic

The latest failed user task records SQLite error 787, `SQLITE_CONSTRAINT_FOREIGNKEY`, with constraint category `foreign_key`. The task has used two publication-only recoveries and is at job attempt 6. Its three extraction and two boundary checkpoints remain validated; eight already-sent model requests remain in the existing ledger. The selected overview is still planned without a downstream job.

The diagnostic used SQLite `mode=ro` and `PRAGMA query_only=ON`. SQLite `quick_check` returned `ok` and `foreign_key_check` found zero violations. No model response body, paper text, source PDF, credentials, or raw SQL parameters were read for this diagnostic, and no formal task was retried or written. A failed transaction can violate a foreign key and roll back while the committed database continues to pass these health checks.

## Reproduction and Fix

With an anonymous PDF, synthetic provider output, and SQLite foreign keys enabled, the old behavior consistently fails during the plan-item `UPDATE` that assigns the new downstream job ID. `_queue_selected_postprocessing()` had added the new `Job` without flushing it before linking `ImportPlanItem.job_id`; autoflush could update the child reference before inserting the parent job.

The fix flushes the new `Job` before assigning the plan-item reference, within the same publication transaction. Foreign-key enforcement stays enabled. Parse/segment publication and downstream queue creation remain atomic, and selected jobs are queued only once.

The earlier batch fixture used bare `create_engine()` without `PRAGMA foreign_keys=ON`; this was the reason prior synthetic tests missed the production write-order defect. The batch fixture now uses production `storage.make_engine()`, asserts foreign-key enforcement, and inserts fixture parents before their children. The previous passing suite is retained as historical evidence and is not described as having covered this constraint.

## Recovery Boundaries

- The ordinary maximum remains two explicit publication recoveries. One additional compatibility recovery is available only for a legacy integer count of 2, an absent recovery-version field, exact safe SQLite 787 foreign-key diagnostics, and phase `publication_failed`.
- Explicit authorization atomically writes cumulative count 3, version `foreign-key-order-1`, and a publication-only intent. It retains old attempts, failed parses, validated checkpoints, page ranges, and model-request usage.
- Both job retry and import-item retry use this policy. Same-key replay does not consume another attempt or create another downstream job. A corrected third attempt that fails or is interrupted does not get another compatibility allowance.
- Every expected checkpoint and frozen range is revalidated; the source PDF's existing stat version is checked before and inside publication, and a successful parse prevents duplicate publication. No SHA-256 parsing prerequisite was added.
- A persisted publication-only intent cannot fall back to provider initialization if quota or checkpoint eligibility changes. Exhausted quota and changed-checkpoint tests confirm zero provider initialization and zero additional model requests.
- The paper panel and task history label this operation “仅重新发布章节（不重发批次）”. The original selected overview/reading generation may subsequently run as a separate task and incur model cost.

## Completed Verification

- Complete engine suite: **586 passed / 1 skipped / 1 warning** in **147.95 seconds**.
- Focused publication, recovery, and import tests: **50 passed** in **16.06 seconds**. These tests overlap the complete engine suite and are not added to its total.
- Desktop suite: **155 passed**.
- Ruff, mypy (**86 engine files**), TypeScript, and ESLint passed.
- Development smoke tests passed through both retry entry points. They used isolated synthetic data, retained successful checkpoints, published without repeating model batches, and preserved the selected downstream queue behavior.

The skipped case and existing Starlette/httpx TestClient deprecation warning remain separate from passing results. Synthetic provider tests and development smoke do not establish real-provider compatibility or scientific extraction quality.

## Final Package and Installed Verification

The final unsigned Windows installer built at **2026-11-19 09:49:08 (Asia/Shanghai)** is [ResearchGraph-Studio-Publication-FK-Fix-0.0.1-x64-setup.exe](../.local/releases/document-fk-order-20261119/ResearchGraph-Studio-Publication-FK-Fix-0.0.1-x64-setup.exe), **160,518,000 bytes**, SHA-256 `D3C0A246954CE1AD0B7D51EBE4A587029B12D201E4131CC19E8C73AF039F869D`. This fingerprint identifies the installer only; no source-PDF hashing prerequisite was added.

Windows PowerShell 5.1 silent installation in a fresh isolated directory passed the comprehensive smoke: schema `lite0013`, synthetic local import, model-document materialization, chapter progress save/readback, legacy cleanup, deletion, and referenced source retention. Model calls: **0**. Evidence: `.local/verify/document-fk-order-20261119/install-smoke/verification.json`.

The installed engine passed both independent publication-recovery entry points. Each case recreated the old foreign-key ordering defect using only synthetic fixture material, then recovered legacy count 2 to count 3/version `foreign-key-order-1`. All five checkpoint rows and their request receipts stayed byte-for-byte unchanged; failed parse history remained; exactly one successful parse and one downstream overview job were created; SQLite foreign-key violations remained zero. GET detail/project/global projections did not write, same-key retry replay was identical, and restarting the packaged engine added no requests or database changes. An intentionally invalid provider snapshot was bypassed by publication-only recovery. Additional model calls and external HTTP requests during recovery: **0**. Evidence: `.local/verify/document-fk-order-20261119/smoke-installed-final/verification.json`. The selected overview in this fixture had network disabled, so its later execution was expected to fail rather than call a provider; the test proves single queue creation, not overview generation.

Native Host tests against the final installed engine passed **14 / 0 failed / 0 ignored**, including packaged-engine startup and restart. The **161** runtime/configuration source fingerprints stayed unchanged through build/install, and the installed sidecar plus **324** internal resource files matched the build. Source private-path/Gitleaks checks passed before final documentation; the final documentation scan is recorded in the development log.

The implementation has not retried or modified the user's formal task, sent a new real model request, or made an external model HTTP request. No commit or push was made. User-native GUI behavior, actual recovery in the user's database, real-provider behavior, and scientific correctness remain unverified. Design: [ADR0055](adr/0055-document-postprocess-foreign-key-order.md).

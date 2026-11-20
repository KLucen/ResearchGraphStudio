# Document Publication Integrity Recovery: Verification

Date: 2026-11-18 (Asia/Shanghai)

Update 2026-11-19: a subsequent safe diagnostic identified SQLite foreign-key error 787. The downstream Job insert/plan-reference order has now been reproduced and fixed; the earlier unknown-constraint statements below describe the earlier diagnostic state. Current root cause, replacement installer, and installed recovery validation: [foreign-key verification](document-fk-order-verification-20261119.md) and [ADR0055](adr/0055-document-postprocess-foreign-key-order.md).

## Finding

The failed 13-page import had all 3 extraction batches and both boundary checkpoints validated before the final publication transaction failed with `IntegrityError`. The earlier task record kept only the exception class, so the exact database constraint cannot be recovered retroactively. The previous read-only health report found SQLite `quick_check = ok`, no foreign-key violations, 4 failed parse history rows with no segments, and the original import/session still present.

The model requests had already been sent and recorded. This failure was at local publication, after extraction and boundary review; it was not a new model response-contract failure. No retry or write to the user's database was performed during this implementation.

## Changes

- Publication `IntegrityError` failures now retain only database dialect, recognized SQLite error code/name, and a fixed constraint category. SQL, driver message, parameters, file paths, model output and PDF text are excluded.
- An explicit retry is available only when the same run/session/job matches, all expected extract and boundary checkpoints remain validated, frozen page ranges agree, and no successful parse exists. The PDF's existing stat-based source version is checked before and within publication. No SHA-256 content hash is added as a parsing prerequisite.
- Publication recovery reads and validates the saved checkpoint JSON, skips provider initialization and PDF upload, and atomically creates the parse and segments. It is limited to two explicit recovery attempts. Selected overview/reading work remains a separate follow-up and can make its own model request.
- Job history distinguishes “仅重新发布章节（不重发批次）”, shows safe database diagnostics when available, and warns that the originally selected overview/reading task may still run.
- The Windows smoke script now handles an empty document-output list without treating `null` as a failed `.Count` access.

## Verification

- Engine: **579 passed, 1 skipped, 1 warning** in 109.30 seconds.
- Focused batch and import retry tests: **34 passed**.
- Desktop: **148 passed** in 14.51 seconds; TypeScript, ESLint, and mypy passed. Mypy checked 86 engine files.
- Ruff passed for `services/engine`, `tests/engine`, and `scripts`.
- Windows NSIS installer built at 2026-11-18 23:51:36: **160,496,071 bytes**.
- PowerShell 5.1 isolated installation smoke passed with schema `lite0013`: engine readiness, synthetic PDF import, model document materialization, chapter progress save/readback, legacy cleanup, paper deletion, and source-file retention. Model calls: **0**.
- The publication-only path itself was exercised with a synthetic SQLite uniqueness failure and 3 validated fake extraction checkpoints; recovery completed with no additional provider calls, persisted a successful parse and segments, retained the failure history, and queued the selected overview once.
- No real model requests, external HTTP requests, private paper content, or credentials were used. No commit or push was made.

The old task's exact violated constraint remains unknown because the earlier build did not record SQLite diagnostics. The original task can be opened after installing the package and retried through the publication-only control if the source version still matches. A selected overview may then run separately and can incur model cost. The installation smoke validates application startup and existing flows; the new recovery behavior is covered by the engine integration test, not by a live provider request.

## Follow-up: Status Projection and Final Package (2026-11-19)

The first recovery build could retain `current_kind=boundary` from the last successful processing stage, which made the final local publication failure look like a boundary-review failure. The read-only task projection now reports `publication` when publication recovery is available or the persisted phase is `publication_failed`; valid legacy boundary recovery continues to report `boundary`. The status component displays publication-specific failed/queued/running text and omits stale boundary page ranges while preserving validated batch and boundary counts.

Regression checks: engine **579 passed / 1 skipped / 1 warning**; desktop **15 files / 151 passed**; TypeScript and ESLint passed. The rebuilt Windows installer was silently installed and verified with Windows PowerShell 5.1 in a fresh isolated directory; schema `lite0013`, synthetic PDF flows, and zero model calls were confirmed.

Final installer: `.local/releases/document-integrity-recovery-20261119-final/ResearchGraph-Studio-Integrity-Recovery-0.0.1-x64-setup.exe`, **160,512,380 bytes**, SHA-256 `DEE14B90B8911661CCD45C4C91C5BC601DC1137C32E1A9B0085A3EB2A1A8B16D`. Isolation evidence: `.local/verify/document-integrity-recovery-20261119/install-smoke/`. No user database or real model was used; no commit or push was made. The original historical SQLite constraint remains unknown.

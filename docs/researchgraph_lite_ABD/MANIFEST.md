# Package manifest

- Project: ResearchGraph Lite A+B+D
- Version: 1.0 (2026-11-09)
- Purpose: lightweight design, prompt/contract spec, progressive migration plan for existing ResearchGraph Studio repo
- Contains: 5 design/engineering docs, 4 task prompts, Pydantic v2 reference contract, 8 generated JSON Schemas, SQLite design sketch, fictional fixtures and test suite
- Contract tests: **16 passed** (`python -m pytest -q tests`), executed in the packaging environment, not in the user's real repository
- Live Zotero/API/Windows integration: **not executed**; requires developer integration and authorized test resources
- Security: no real API key, private paper PDF, notebook vault, or actual user database included

## Critical non-goals

This is not a drop-in migration or proof of feature completion. `schemas/sqlite_reference.sql` is a schema design reference; the active Lite application initializes the separate database from the `lite0001` baseline and currently runs at Alembic head `lite0007` (including A01 section-guide, D01 grounded-QA, D02 search-keyword, shared model connections, optional PDF translation and managed service settings). It does not migrate old Graph data. Use `backup/pre-lite-refactor` for historical recovery. The original optional bridge is specified in [ADR0036](../adr/0036-optional-pdf-translation-bridge.md), with on-demand process ownership and shutdown added by [ADR0037](../adr/0037-managed-translation-server.md). Existing translation settings retain manual mode after migration; new installations without a settings row recommend managed mode after the user installs the external environment and selects its paths. Its external runtime and real translation quality have not been accepted by the reference-contract tests.

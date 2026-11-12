# Package manifest

- Project: ResearchGraph Lite A+B+D
- Version: 1.0 (2026-11-09)
- Purpose: lightweight design, prompt/contract spec, progressive migration plan for existing ResearchGraph Studio repo
- Contains: 5 design/engineering docs, 4 task prompts, Pydantic v2 reference contract, 8 generated JSON Schemas, SQLite design sketch, fictional fixtures and test suite
- Contract tests: **16 passed** (`python -m pytest -q tests`), executed in the packaging environment, not in the user's real repository
- Live Zotero/API/Windows integration: **not executed**; requires developer integration and authorized test resources
- Security: no real API key, private paper PDF, notebook vault, or actual user database included

## Critical non-goals

This is not a drop-in migration or proof of feature completion. `schemas/sqlite_reference.sql` is a schema design reference; the active Lite application initializes a separate database from the `lite0001` baseline and retains Alembic head `lite0008`. Active features include A01 section-guide, D01 grounded-QA, D02 search-keyword and shared model connections. Historical translation tables and migrations remain for existing-database compatibility. PDF translation has been withdrawn under [ADR0040](../adr/0040-remove-pdf-translation.md); its active APIs, execution runtime and bundled resources are removed. No database downgrade or deletion of existing user data is part of that withdrawal. Old complete Graph data is not migrated into Lite; use `backup/pre-lite-refactor` for historical recovery. Reference-contract test results do not establish live Provider quality, current Windows integration or feature acceptance.

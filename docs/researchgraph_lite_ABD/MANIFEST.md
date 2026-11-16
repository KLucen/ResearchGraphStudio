# Package manifest

- Project: ResearchGraph Lite A+B+D
- Version: 1.0 (2026-11-09)
- Purpose: lightweight design, prompt/contract spec, progressive migration plan for existing ResearchGraph Studio repo
- Contains: 5 design/engineering docs, 7 task prompts (including A02–A04 additions), Pydantic v2 reference contract, 8 generated reference JSON Schemas, SQLite design sketch, fictional fixtures and test suite
- Contract tests: **16 passed** (`python -m pytest -q tests`), executed in the packaging environment, not in the user's real repository
- Live Zotero/API/Windows integration: **not executed**; requires developer integration and authorized test resources
- Security: no real API key, private paper PDF, notebook vault, or actual user database included

## Critical non-goals

This is not a drop-in migration or proof of feature completion. `schemas/sqlite_reference.sql` is a schema design reference; the active Lite application initializes a separate database from the `lite0001` baseline and upgrades additively to Alembic head `lite0010`. The [section-reading addendum](ResearchGraph_Lite_Section_CloseReading_Bilingual_Annotation.md), incorporated on 2026-11-14, extends P2 with range-scoped A02 bilingual analysis, local understanding state, explicit A03 checks and optional A01 reader context. [ADR0042](../adr/0042-paper-reading-document-and-notes.md) adds a local reading projection and makes explicit, single-request A04 whole-paper notes the default reading workflow; A02 results remain available as history. Runtime schemas live in engine contracts and exported OpenAPI. Historical PDF translation tables remain for compatibility; the removed PDF translation service/runtime is not restored. See [ADR0040](../adr/0040-remove-pdf-translation.md) and [ADR0041](../adr/0041-section-bilingual-close-reading.md). Old complete Graph data is not migrated into Lite; use `backup/pre-lite-refactor` for historical recovery. Reference-contract test results do not establish live Provider quality, current Windows integration or feature acceptance.

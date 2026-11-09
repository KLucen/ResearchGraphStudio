# Package manifest

- Project: ResearchGraph Lite A+B+D
- Version: 1.0 (2026-11-09)
- Purpose: lightweight design, prompt/contract spec, progressive migration plan for existing ResearchGraph Studio repo
- Contains: 5 design/engineering docs, 4 task prompts, Pydantic v2 reference contract, 8 generated JSON Schemas, SQLite additive schema sketch, fictional fixtures, test suite, and concise Codex continuation instruction
- Contract tests: **16 passed** (`python -m pytest -q tests`), executed in the packaging environment, not in the user's real repository
- Live Zotero/API/Windows integration: **not executed**; requires developer integration and authorized test resources
- Security: no real API key, private paper PDF, notebook vault, or actual user database included

## Critical non-goals

This is not a drop-in migration or proof of feature completion. `schemas/sqlite_reference.sql` is a schema design reference; generate reversible migrations against the existing repository after inspecting live table definitions. Old Graph data should be retained and readable.

-- ResearchGraph Lite additive schema sketch. DO NOT run against user DB without
-- mapping current project/document tables + writing a reversible Alembic migration.
-- Source of truth for paper/section/span/document_versions stays in existing tables.

CREATE TABLE IF NOT EXISTS lite_paper_cards (
  id TEXT PRIMARY KEY,
  paper_id TEXT NOT NULL,
  document_version_id TEXT NOT NULL,
  model_run_id TEXT NOT NULL,
  prompt_version TEXT NOT NULL,
  cache_key TEXT NOT NULL UNIQUE,
  payload_json TEXT NOT NULL,
  state TEXT NOT NULL CHECK (state IN ('succeeded','stale','failed')),
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_lite_cards_paper ON lite_paper_cards(paper_id, document_version_id);

CREATE TABLE IF NOT EXISTS lite_section_guides (
  id TEXT PRIMARY KEY,
  section_id TEXT NOT NULL,
  document_version_id TEXT NOT NULL,
  depth TEXT NOT NULL CHECK (depth IN ('quick','standard','deep')),
  model_run_id TEXT NOT NULL,
  cache_key TEXT NOT NULL UNIQUE,
  payload_json TEXT NOT NULL,
  state TEXT NOT NULL CHECK (state IN ('succeeded','stale','failed')),
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_lite_guides_section ON lite_section_guides(section_id, depth);

CREATE TABLE IF NOT EXISTS lite_qa_records (
  id TEXT PRIMARY KEY,
  paper_id TEXT NOT NULL,
  document_version_id TEXT NOT NULL,
  section_id TEXT,
  scope TEXT NOT NULL CHECK (scope IN ('selection','section','paper')),
  question TEXT NOT NULL,
  retrieval_span_ids_json TEXT NOT NULL,
  result_json TEXT NOT NULL,
  model_run_id TEXT NOT NULL,
  cache_key TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_lite_qa_paper ON lite_qa_records(paper_id, created_at);

CREATE TABLE IF NOT EXISTS lite_cache_entries (
  cache_key TEXT PRIMARY KEY,
  task_kind TEXT NOT NULL CHECK (task_kind IN ('card','guide','qa','keywords')),
  document_version_id TEXT NOT NULL,
  prompt_version TEXT NOT NULL,
  result_ref TEXT NOT NULL,
  input_fingerprint TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('succeeded','stale')),
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lite_token_usage (
  id TEXT PRIMARY KEY,
  task_run_id TEXT NOT NULL,
  paper_id TEXT NOT NULL,
  task_kind TEXT NOT NULL,
  provider TEXT NOT NULL,
  model_id TEXT NOT NULL,
  input_tokens INTEGER,
  output_tokens INTEGER,
  usage_source TEXT NOT NULL CHECK (usage_source IN ('provider','estimated','unknown')),
  retry_number INTEGER NOT NULL DEFAULT 0,
  cache_hit INTEGER NOT NULL DEFAULT 0,
  latency_ms INTEGER,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  CHECK(input_tokens IS NULL OR input_tokens >= 0),
  CHECK(output_tokens IS NULL OR output_tokens >= 0)
);
CREATE INDEX IF NOT EXISTS ix_lite_usage_paper ON lite_token_usage(paper_id, created_at);

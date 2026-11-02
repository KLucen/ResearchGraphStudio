-- Reference design only, NOT an unconditional migration script.
-- Integrate with existing Alembic/SQLite schema; preserve old IDs and review history.
-- Apply migration to a BACKUP/test DB before touching a user's active project.

CREATE TABLE IF NOT EXISTS graph_layouts (
  project_id TEXT NOT NULL,
  view_id TEXT NOT NULL,
  node_id TEXT NOT NULL,
  x REAL NOT NULL,
  y REAL NOT NULL,
  pinned INTEGER NOT NULL DEFAULT 0 CHECK (pinned IN (0, 1)),
  layout_version INTEGER NOT NULL DEFAULT 1,
  updated_at TEXT NOT NULL,
  PRIMARY KEY(project_id, view_id, node_id)
);

CREATE TABLE IF NOT EXISTS graph_viewports (
  project_id TEXT NOT NULL,
  view_id TEXT NOT NULL,
  zoom REAL NOT NULL DEFAULT 1.0,
  pan_x REAL NOT NULL DEFAULT 0,
  pan_y REAL NOT NULL DEFAULT 0,
  PRIMARY KEY(project_id, view_id)
);

CREATE TABLE IF NOT EXISTS extraction_batches (
  batch_key TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  document_version_id TEXT NOT NULL,
  chunk_id TEXT NOT NULL,
  input_hash TEXT NOT NULL,
  prompt_version TEXT NOT NULL,
  schema_version TEXT NOT NULL,
  model_id TEXT NOT NULL,
  state TEXT NOT NULL,
  committed_revision INTEGER,
  attempts INTEGER NOT NULL DEFAULT 0,
  last_error_code TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_batches_project_state ON extraction_batches(project_id, state);

CREATE TABLE IF NOT EXISTS graph_outbox (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  revision INTEGER NOT NULL,
  event_type TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  delivered_at TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_graph_outbox_project_revision ON graph_outbox(project_id, revision);

CREATE TABLE IF NOT EXISTS knowledge_display_metadata (
  project_id TEXT NOT NULL,
  entity_kind TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  label_zh TEXT,
  label_en TEXT,
  summary_zh TEXT,
  summary_en TEXT,
  translation_status TEXT,
  translator_prompt_version TEXT,
  updated_at TEXT NOT NULL,
  PRIMARY KEY(project_id, entity_kind, entity_id)
);

-- Existing KnowledgeStore/domain tables should remain authoritative.
-- Do NOT copy all domain entities into separate v3 tables just for display.
-- A layout drag updates graph_layouts only; NOT the graph knowledge revision.

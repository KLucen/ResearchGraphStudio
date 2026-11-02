-- DESIGN v3.3 ONLY. NOT an Alembic migration and never run on the user database.
-- Existing knowledge_nodes, attachment_revisions, model_runs and source assertions
-- remain authoritative. No parallel candidate-content or evidence database.
-- Existing parent tables are assumed; tests create minimal synthetic parents.
-- Store must additionally enforce project/document ownership, typed associations,
-- membership reachability, source/quality gates and optimistic revision checks.
PRAGMA foreign_keys = ON;

CREATE TABLE reading_quality_assessments (
  node_id TEXT NOT NULL REFERENCES knowledge_nodes(id),
  node_revision INTEGER NOT NULL CHECK(node_revision > 0),
  policy_version TEXT NOT NULL,
  assessment_json TEXT NOT NULL CHECK(json_valid(assessment_json)),
  model_run_id TEXT REFERENCES model_runs(id),
  PRIMARY KEY(node_id, node_revision, policy_version)
);

CREATE TABLE reading_builds (
  id TEXT PRIMARY KEY,
  document_version_id TEXT NOT NULL REFERENCES attachment_revisions(id),
  input_signature TEXT NOT NULL,
  manifest_json TEXT NOT NULL CHECK(json_valid(manifest_json)),
  state TEXT NOT NULL CHECK(state IN ('queued','running','failed','cancelled','complete')),
  UNIQUE(document_version_id, input_signature)
);

CREATE TABLE reading_stage_commits (
  operation_key TEXT PRIMARY KEY,
  build_id TEXT NOT NULL REFERENCES reading_builds(id),
  stage TEXT NOT NULL CHECK(stage IN ('indexing','extracting','integrating','selecting','publishing')),
  input_hash TEXT NOT NULL,
  result_json TEXT NOT NULL CHECK(json_valid(result_json)),
  model_run_id TEXT REFERENCES model_runs(id)
);

CREATE TABLE reading_unit_versions (
  unit_id TEXT NOT NULL,
  revision INTEGER NOT NULL CHECK(revision > 0),
  document_version_id TEXT NOT NULL REFERENCES attachment_revisions(id),
  root_claim_id TEXT NOT NULL REFERENCES knowledge_nodes(id),
  integration_run_id TEXT REFERENCES model_runs(id),
  PRIMARY KEY(unit_id, revision)
);

CREATE TABLE reading_unit_members (
  unit_id TEXT NOT NULL,
  unit_revision INTEGER NOT NULL,
  member_id TEXT NOT NULL REFERENCES knowledge_nodes(id),
  association_ids_json TEXT NOT NULL CHECK(json_valid(association_ids_json)),
  PRIMARY KEY(unit_id, unit_revision, member_id),
  FOREIGN KEY(unit_id, unit_revision) REFERENCES reading_unit_versions(unit_id, revision)
);

CREATE TABLE reading_selections (
  id TEXT PRIMARY KEY,
  document_version_id TEXT NOT NULL REFERENCES attachment_revisions(id),
  knowledge_revision INTEGER NOT NULL CHECK(knowledge_revision >= 0),
  selection_revision INTEGER NOT NULL CHECK(selection_revision > 0),
  policy_version TEXT NOT NULL,
  density TEXT NOT NULL CHECK(density IN ('concise','standard','detailed')),
  build_state TEXT NOT NULL CHECK(build_state IN ('partial','complete')),
  coverage_gaps_json TEXT NOT NULL CHECK(json_valid(coverage_gaps_json)),
  UNIQUE(document_version_id, selection_revision),
  UNIQUE(document_version_id, id)
);

CREATE TABLE reading_selection_entries (
  selection_id TEXT NOT NULL REFERENCES reading_selections(id),
  candidate_id TEXT NOT NULL REFERENCES knowledge_nodes(id),
  graph_role TEXT NOT NULL CHECK(graph_role IN ('core','supporting','retrieval_only')),
  selected_by TEXT NOT NULL CHECK(selected_by IN ('automatic','user_preference')),
  reason TEXT NOT NULL,
  PRIMARY KEY(selection_id, candidate_id)
);

CREATE TABLE reading_selection_units (
  selection_id TEXT NOT NULL REFERENCES reading_selections(id),
  unit_id TEXT NOT NULL,
  unit_revision INTEGER NOT NULL,
  PRIMARY KEY(selection_id, unit_id),
  FOREIGN KEY(unit_id, unit_revision) REFERENCES reading_unit_versions(unit_id, revision)
);

CREATE TABLE reading_active_selections (
  document_version_id TEXT PRIMARY KEY REFERENCES attachment_revisions(id),
  selection_id TEXT NOT NULL,
  FOREIGN KEY(document_version_id, selection_id) REFERENCES reading_selections(document_version_id, id)
);

CREATE TABLE reading_selection_preferences (
  document_version_id TEXT NOT NULL REFERENCES attachment_revisions(id),
  candidate_id TEXT NOT NULL REFERENCES knowledge_nodes(id),
  preference_revision INTEGER NOT NULL CHECK(preference_revision > 0),
  action TEXT NOT NULL CHECK(action IN ('include_core','exclude_core','reset_automatic')),
  reason TEXT NOT NULL,
  PRIMARY KEY(document_version_id, candidate_id, preference_revision)
);

CREATE INDEX reading_unit_roots ON reading_unit_versions(document_version_id, root_claim_id);
CREATE INDEX reading_selection_roles ON reading_selection_entries(selection_id, graph_role);

-- New workflow has NO review queue/status/table. Historical review tables remain.
-- Quality/unit/selection snapshots append rather than overwrite; only active pointer
-- changes after CAS + complete validation in one KnowledgeStore transaction.
-- Reuse existing graph layout and knowledge event tables. Layout never edits these.
-- FTS indexes all valid candidates, not just graph_role='core'. No source cascades.

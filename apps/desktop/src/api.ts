import { invoke } from "@tauri-apps/api/core";
import type { components } from "../../../packages/contracts/generated";

export type Project = components["schemas"]["ProjectView"];
export type Job = components["schemas"]["JobView"];
export type JobList = components["schemas"]["JobList"];
export type Health = components["schemas"]["Health"];
export type ProjectList = components["schemas"]["ProjectList"];
export type PaperList = components["schemas"]["PaperList"];
export type PaperDetail = components["schemas"]["PaperDetail"];
export type ChunkList = components["schemas"]["ChunkList"];
export type Source = components["schemas"]["SourceView"];
export type Structure = components["schemas"]["DocumentStructure"];
export type KnowledgeList = components["schemas"]["KnowledgeList"];
export type KnowledgeNode = components["schemas"]["NodeView"];
export type NodeDetail = components["schemas"]["NodeDetail"];
export type Evidence = components["schemas"]["EvidenceView"];
export type ModelRun = components["schemas"]["ModelRunView"];
export type ReviewRequest = components["schemas"]["ReviewRequest"];
export type NoteRoot = { id: string; path: string; active: boolean };
export type Annotation = {
  id: string;
  text: string;
  comment: string;
  anchor_status: string;
  source_item_key: string;
  annotation_key: string;
  evidence_id: string | null;
};

export interface HostStatus {
  running: boolean;
  data_dir: string;
  error: string | null;
}

export async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  key?: string,
): Promise<T> {
  try {
    return await invoke<T>("engine_request", {
      method,
      path,
      body: body ?? null,
      idempotencyKey: key ?? null,
    });
  } catch (error) {
    throw new Error(
      typeof error === "string"
        ? error
        : "本地服务暂时不可用，请检查连接后重试",
    );
  }
}
export const api = {
  structure: (id: string) =>
    request<Structure>("GET", `/api/v1/revisions/${id}/structure`),
  knowledge: (id: string) =>
    request<KnowledgeList>(
      "GET",
      `/api/v1/revisions/${id}/knowledge?include_test_data=false&current_schema_only=true`,
    ),
  node: (id: string) =>
    request<NodeDetail>("GET", `/api/v1/knowledge/nodes/${id}`),
  preview: (id: string) =>
    request<components["schemas"]["Preview"]>(
      "GET",
      `/api/v1/evidence/${id}/preview`,
    ),
  extract: (
    id: string,
    provider: "mock" | "configured" | "project",
    allowNetwork: boolean,
    pipeline:
      "paper-reading-v1" | "unified-v3" | "legacy-v2" = "paper-reading-v1",
  ) =>
    request<Job>(
      "POST",
      "/api/v1/knowledge/extract",
      {
        document_version_id: id,
        provider,
        allow_network: allowNetwork,
        pipeline,
      },
      crypto.randomUUID(),
    ),
  review: (body: ReviewRequest) =>
    request<KnowledgeNode>(
      "POST",
      "/api/v1/knowledge/reviews",
      body,
      crypto.randomUUID(),
    ),
  runs: (id: string) =>
    request<ModelRun[]>("GET", `/api/v1/revisions/${id}/runs`),
  providers: () =>
    request<{
      configured: boolean;
      model: string | null;
      mock: string;
      transmitted_data: string;
    }>("GET", "/api/v1/providers"),
  noteRoots: (id: string) =>
    request<NoteRoot[]>("GET", `/api/v1/projects/${id}/note-roots`),
  authorizeNotes: (projectId: string) =>
    invoke<NoteRoot | null>("authorize_notes_directory", {
      projectId,
      idempotencyKey: crypto.randomUUID(),
    }),
  noteAction: (id: string, action: "scan" | "revoke") =>
    request<{ added?: number; skipped?: number; active?: boolean }>(
      "POST",
      `/api/v1/integrations/obsidian/${id}/${action}`,
      null,
      crypto.randomUUID(),
    ),
  notes: (id: string) =>
    request<
      {
        id: string;
        relative_path: string;
        sha256: string;
        text: string;
        authorship: string;
      }[]
    >("GET", `/api/v1/integrations/obsidian/${id}/notes`),
  zoteroStatus: () =>
    request<{ connected: boolean; error?: string }>(
      "GET",
      "/api/v1/integrations/zotero/status",
    ),
  zoteroItems: (start = 0) =>
    request<{ key: string; data: { title?: string; itemType?: string } }[]>(
      "GET",
      `/api/v1/integrations/zotero/items?library=users/0&start=${start}`,
    ),
  annotations: (id: string) =>
    request<Annotation[]>("GET", `/api/v1/revisions/${id}/annotations`),
  importAnnotations: (id: string, itemKey: string, attachmentKey: string) =>
    request<{ added: number; unresolved: number }>(
      "POST",
      "/api/v1/integrations/zotero/annotations",
      {
        document_version_id: id,
        library: "users/0",
        item_key: itemKey,
        attachment_key: attachmentKey,
      },
      crypto.randomUUID(),
    ),
  checkSource: (source: Source) =>
    request<Job>(
      "POST",
      `/api/v1/sources/${source.id}/check`,
      { expected_generation: source.generation },
      crypto.randomUUID(),
    ),
  relocateSource: (source: Source) =>
    invoke<Job | null>("relocate_source_file", {
      sourceId: source.id,
      expectedGeneration: source.generation,
      idempotencyKey: crypto.randomUUID(),
    }),
  projectJobs: (projectId: string, cursor: string | null = null) =>
    request<JobList>(
      "GET",
      `/api/v1/projects/${projectId}/jobs?limit=10${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`,
    ),
  importPdf: (projectId: string, mode: "reference" | "managed") =>
    invoke<Job | null>("import_pdf_file", {
      projectId,
      mode,
      idempotencyKey: crypto.randomUUID(),
    }),
  papers: (projectId: string, cursor = 0) =>
    request<PaperList>(
      "GET",
      `/api/v1/projects/${projectId}/papers?cursor=${cursor}&limit=50`,
    ),
  paper: (paperId: string) =>
    request<PaperDetail>("GET", `/api/v1/papers/${paperId}`),
  chunks: (revisionId: string, cursor = 0) =>
    request<ChunkList>(
      "GET",
      `/api/v1/revisions/${revisionId}/chunks?cursor=${cursor}&limit=50`,
    ),
  host: () => invoke<HostStatus>("host_status"),
  restart: () => invoke<HostStatus>("restart_engine"),
  health: () => request<Health>("GET", "/api/v1/health"),
  projects: (cursor = 0) =>
    request<ProjectList>("GET", `/api/v1/projects?cursor=${cursor}&limit=50`),
  createProject: (body: { name: string; description: string }, key: string) =>
    request<Project>("POST", "/api/v1/projects", body, key),
  jobs: () => request<Job[]>("GET", "/api/v1/jobs"),
  diagnose: (key: string) =>
    request<Job>("POST", "/api/v1/jobs", { kind: "diagnostics" }, key),
  jobAction: (id: string, action: "cancel" | "retry", key: string) =>
    request<Job>("POST", `/api/v1/jobs/${id}/${action}`, null, key),
};

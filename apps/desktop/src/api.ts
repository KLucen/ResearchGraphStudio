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

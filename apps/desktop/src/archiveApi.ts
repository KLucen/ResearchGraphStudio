import { request } from "./api";

export const archiveKinds = {
  paper: "项目论文",
  knowledge_paper: "论文知识",
  knowledge_collection: "知识专题",
  model_connection: "模型提供商",
  model_profile: "模型配置",
  job: "任务记录",
  paper_legacy_content: "旧本地解析",
} as const;

export type ArchiveKind = keyof typeof archiveKinds;
export type ArchiveItem = {
  id: string;
  kind: ArchiveKind;
  target_id: string;
  title: string;
  archived_at: string;
  project_id: string | null;
  status: "archived" | "purging";
};

export type ArchivePurgeResult = {
  ok: boolean;
  status?: "purged" | "purging";
  retained_managed_files?: number;
  pending_managed_files?: number;
};

export const archiveApi = {
  list(kind: ArchiveKind | "", offset: number, limit: number) {
    const query = new URLSearchParams({
      offset: String(offset),
      limit: String(limit),
    });
    if (kind) query.set("kind", kind);
    return request<{ items: ArchiveItem[]; total: number }>(
      "GET",
      `/api/v1/archive?${query}`,
    );
  },
  stage(kind: ArchiveKind, targetId: string) {
    return request<ArchiveItem>(
      "POST",
      "/api/v1/archive",
      { kind, target_id: targetId },
      crypto.randomUUID(),
    );
  },
  restore(id: string) {
    return request<{ ok: true }>(
      "POST",
      `/api/v1/archive/${encodeURIComponent(id)}/restore`,
      {},
      crypto.randomUUID(),
    );
  },
  purge(id: string) {
    return request<ArchivePurgeResult>(
      "DELETE",
      `/api/v1/archive/${encodeURIComponent(id)}`,
      undefined,
      crypto.randomUUID(),
    );
  },
};

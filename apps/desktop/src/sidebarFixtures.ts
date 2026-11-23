import type { Paper, Project } from "./api";

export const sidebarProjects: Project[] = Array.from(
  { length: 5 },
  (_, index) => ({
    id: `sidebar-project-${index + 1}`,
    name: `合成研究项目 ${index + 1}`,
    description: "可分发侧栏回归材料",
    experience_mode: "lite",
    created_at: "2026-11-21T00:00:00Z",
  }),
);

export const sidebarPapers = (projectId: string): Paper[] =>
  Array.from({ length: 24 }, (_, index) => ({
    id: `${projectId}-paper-${index + 1}`,
    project_id: projectId,
    title: `合成论文 ${String(index + 1).padStart(2, "0")}：面向长期研究的多来源知识组织与证据推理方法及跨论文联系分析`,
    created_at: "2026-11-21T00:00:00Z",
  }));

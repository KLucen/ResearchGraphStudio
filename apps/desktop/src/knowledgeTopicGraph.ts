import { request } from "./api";
import type { KnowledgePaper, KnowledgeReport } from "./knowledgeApi";

export type ExternalTopicPaper = {
  id: string;
  title: string;
  version_id: string;
};

export const topicGraphApi = {
  externalPapers: (collectionId: string, paperIds: string[]) =>
    request<{ items: ExternalTopicPaper[]; has_more: boolean }>(
      "GET",
      `/api/v1/knowledge/collections/${encodeURIComponent(collectionId)}/external-papers?${new URLSearchParams({ paper_ids: paperIds.join(",") })}`,
    ),
};

const candidateLimit = 48;

export function topicContextCandidates(
  papers: KnowledgePaper[],
  reports: KnowledgeReport[],
) {
  const visiblePapers = new Set(papers.map((paper) => paper.id));
  const visibleVersions = new Set(
    papers.flatMap((paper) =>
      paper.archived || !paper.current_version
        ? []
        : [paper.current_version.id],
    ),
  );
  const ids = new Set<string>();
  for (const report of reports) {
    if (report.stale) continue;
    const dependencies = new Map<string, string>();
    if (Array.isArray(report.dependencies)) {
      for (const dependency of report.dependencies) {
        if (
          typeof dependency?.version_id === "string" &&
          typeof dependency.library_paper_id === "string"
        ) {
          dependencies.set(dependency.version_id, dependency.library_paper_id);
        }
      }
    }
    if (report.version_id && report.library_paper_id)
      dependencies.set(report.version_id, report.library_paper_id);

    for (const relation of report.relations ?? []) {
      const source = relation.source_version_id;
      const target = relation.target_version_id;
      if (!source || !target) continue;
      const sourceVisible = visibleVersions.has(source);
      const targetVisible = visibleVersions.has(target);
      if (sourceVisible === targetVisible) continue;
      const paperId = sourceVisible
        ? (relation.target_library_paper_id ?? dependencies.get(target))
        : (relation.source_library_paper_id ?? dependencies.get(source));
      if (!paperId || visiblePapers.has(paperId) || ids.has(paperId)) continue;
      if (ids.size === candidateLimit) return { ids: [...ids], limited: true };
      ids.add(paperId);
    }
  }
  return { ids: [...ids], limited: false };
}

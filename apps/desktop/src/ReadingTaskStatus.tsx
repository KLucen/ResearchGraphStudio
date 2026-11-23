import { useQuery } from "@tanstack/react-query";
import { api, type ImportSession, type Job } from "./api";
import { readingTaskLabels } from "./jobProgress";

export function isActiveReadingTask(status?: string): boolean {
  return status === "queued" || status === "running";
}

export function useModelImportSession(
  sessionId: string | undefined,
  connected: boolean,
) {
  return useQuery({
    queryKey: ["model-document-import-session", sessionId],
    queryFn: () => api.importSession(sessionId!),
    enabled: connected && !!sessionId,
    retry: false,
    // A failed sibling can leave the whole session failed during another task.
    refetchInterval: (query) =>
      query.state.data?.items.some((item) =>
        isActiveReadingTask(item.status),
      ) || query.state.data?.status === "planned"
        ? 1500
        : false,
  });
}

export function ReadingTaskStatus({
  connected,
  session,
  parseJob,
  submittedParse,
}: {
  connected: boolean;
  session?: ImportSession;
  parseJob?: Job;
  submittedParse?: "local" | "model";
}) {
  const overviewJobId = session?.items.find(
    (item) =>
      item.item_kind === "paper_overview" && isActiveReadingTask(item.status),
  )?.job_id;
  const overviewTask = useQuery({
    queryKey: ["job", overviewJobId],
    queryFn: () => api.job(overviewJobId!),
    enabled: connected && !!overviewJobId,
    select: (job) => job.reading_task,
    staleTime: Infinity,
    retry: false,
  });
  const tasks = new Set<string>();
  if (submittedParse && (!parseJob || isActiveReadingTask(parseJob.status))) {
    tasks.add(
      submittedParse === "local"
        ? "本地解析"
        : readingTaskLabels.document_parse,
    );
  }
  for (const item of session?.items ?? []) {
    if (
      !isActiveReadingTask(item.status) ||
      (parseJob &&
        item.job_id === parseJob.id &&
        !isActiveReadingTask(parseJob.status))
    ) {
      continue;
    }
    const kind =
      item.item_kind === "paper_overview" &&
      overviewTask.data === "paper_card_set"
        ? "paper_card_set"
        : item.item_kind;
    tasks.add(readingTaskLabels[kind]);
  }
  if (!tasks.size) return null;
  return <p role="status">任务进行中：{[...tasks].join("、")}</p>;
}

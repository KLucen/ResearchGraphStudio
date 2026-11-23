import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type ReadingParagraph } from "./api";
import { PaperCardSet } from "./PaperCardSet";
import "./paperWorkspace.css";

const errorText = (value: unknown) =>
  value instanceof Error ? value.message : String(value);

type PaperOverviewProps = {
  paperId: string;
  revisionId: string;
  projectId: string;
  connected: boolean;
  source?: "local" | "model";
  showActiveTask?: boolean;
  initialNodeId?: string;
  onOpenSection?: (sectionId: string, paragraphId?: string) => void;
  onAskParagraph?: (sectionId: string, paragraph: ReadingParagraph) => void;
};

export function PaperOverview(props: PaperOverviewProps) {
  return (
    <PaperOverviewSession
      key={`${props.source ?? "local"}:${props.paperId}:${props.revisionId}`}
      {...props}
    />
  );
}

function PaperOverviewSession({
  paperId,
  revisionId,
  projectId,
  connected,
  source = "local",
  showActiveTask = true,
  initialNodeId = "",
  onOpenSection,
}: PaperOverviewProps) {
  const client = useQueryClient();
  const queryName = source === "model" ? "model-overview" : "overview";
  const [allowNetwork, setAllowNetwork] = useState(false);
  const previousStatus = useRef<string | undefined>(undefined);
  const overview = useQuery({
    queryKey: [queryName, paperId, revisionId],
    queryFn: () =>
      source === "model"
        ? api.modelOverview(paperId, revisionId)
        : api.overview(paperId, revisionId),
    enabled: connected,
    refetchInterval: (query) =>
      query.state.data?.status === "PENDING" ? 1500 : false,
  });
  const generate = useMutation({
    mutationFn: ({
      retryFailed,
      forceRegenerate,
    }: {
      retryFailed: boolean;
      forceRegenerate: boolean;
    }) =>
      (source === "model" ? api.generateModelOverview : api.generateOverview)(
        paperId,
        revisionId,
        allowNetwork,
        retryFailed,
        forceRegenerate,
      ),
    onSuccess: (value) => {
      setAllowNetwork(false);
      client.setQueryData([queryName, paperId, revisionId], value);
      if (source === "model")
        void client.invalidateQueries({
          queryKey: ["model-document-import-session"],
        });
    },
    onSettled: () => {
      void client.invalidateQueries({ queryKey: ["lite-usage", projectId] });
      void client.invalidateQueries({ queryKey: ["jobs", projectId] });
    },
  });
  const data = overview.data;
  const recovery = useMutation({
    mutationFn: (outputId: string) =>
      api.recoverModelDocumentOutput(paperId, outputId),
    onSuccess: () => {
      setAllowNetwork(false);
      return client.invalidateQueries({
        queryKey: [queryName, paperId, revisionId],
      });
    },
  });
  const cards =
    data?.card_set?.schema_version === "paper-card-set-2"
      ? data.card_set
      : null;
  const currentVersion = data?.schema_version === "paper-card-set-2";
  const completed = currentVersion && data.status === "COMPLETED" && !!cards;
  const partial = currentVersion && data.status === "PARTIAL" && !!cards;
  const pending = currentVersion && data.status === "PENDING";
  const failed = currentVersion && data.status === "FAILED";
  const earlierPartial =
    failed && !!data.display_result_id && !!cards
      ? data.display_recovery_summary
      : null;
  const displayedResultId = data?.display_result_id ?? data?.id;
  const recoverySummary = data?.recovery_summary;
  const recoveryId =
    source === "model" && failed && data.local_recovery_available
      ? data.id
      : null;
  useEffect(() => {
    if (
      previousStatus.current === "PENDING" &&
      data?.status &&
      data.status !== "PENDING"
    ) {
      void client.invalidateQueries({ queryKey: ["lite-usage", projectId] });
      void client.invalidateQueries({ queryKey: ["jobs", projectId] });
    }
    previousStatus.current = data?.status ?? undefined;
  }, [client, data?.status, projectId]);
  const showGeneration = !pending && !overview.isPending;
  const generation = (
    <div className="import-controls card-set-generation">
      <label>
        <input
          type="checkbox"
          checked={allowNetwork}
          onChange={(event) => setAllowNetwork(event.target.checked)}
        />
        允许向已配置模型发送本篇论文内容
      </label>
      <button
        type="button"
        className="button primary"
        disabled={
          !connected ||
          !allowNetwork ||
          generate.isPending ||
          recovery.isPending
        }
        onClick={() =>
          generate.mutate({
            retryFailed: !!failed,
            forceRegenerate:
              completed ||
              partial ||
              (!!data?.schema_version && !currentVersion),
          })
        }
      >
        {generate.isPending
          ? "正在提交…"
          : completed || partial || failed
            ? "重新生成卡片集"
            : "生成论文卡片集"}
      </button>
      <small className="muted">
        生成时使用所选解析材料，可能产生模型费用。
      </small>
    </div>
  );

  return (
    <section className="settings-card paper-overview" aria-label="论文概览">
      <div className="settings-title">
        <h3>论文概览</h3>
        {completed && <span className="pill">详细知识卡片集 · v2</span>}
      </div>
      {overview.isPending && connected && (
        <p role="status">正在读取论文卡片集…</p>
      )}
      {overview.error && (
        <p role="alert" className="error-text">
          {errorText(overview.error)}
        </p>
      )}
      {overview.isSuccess && !currentVersion && (
        <p className="quality-note">
          尚未生成新版论文卡片集。明确允许一次模型调用后，可重新生成文章总览、卡片介绍与逐条有据的分类卡片。
        </p>
      )}
      {pending && showActiveTask && (
        <p role="status">任务进行中：论文卡片集生成</p>
      )}
      {failed && (
        <div role="alert" className="quality-note">
          <strong>卡片集生成失败</strong>
          <p>
            {recoveryId && recoverySummary
              ? `${recoverySummary.invalid_evidence} 条引文未通过来源校验。`
              : data.error || data.error_code || "模型响应未通过格式或来源校验"}
          </p>
        </div>
      )}
      {recoveryId && recoverySummary && (
        <div className="quality-note">
          <p>
            本机可恢复 {recoverySummary.retained_cards} /{" "}
            {recoverySummary.original_cards} 张卡片，排除{" "}
            {recoverySummary.excluded_cards} 张未通过引文校验的卡片。
          </p>
          <button
            type="button"
            className="button secondary"
            disabled={!connected || recovery.isPending || generate.isPending}
            onClick={() => recovery.mutate(recoveryId)}
          >
            {recovery.isPending ? "正在核验并恢复…" : "本机恢复已校验卡片"}
          </button>
          <p className="muted">使用已保留的响应，模型请求为 0。</p>
        </div>
      )}
      {recovery.error && (
        <p role="alert" className="error-text">
          {errorText(recovery.error)}
        </p>
      )}
      {showGeneration &&
        (completed || partial ? (
          <details
            className="reading-secondary-actions"
            onToggle={(event) => {
              if (!event.currentTarget.open) setAllowNetwork(false);
            }}
          >
            <summary>更多卡片操作</summary>
            {generation}
          </details>
        ) : (
          generation
        ))}
      {generate.error && (
        <p role="alert" className="error-text">
          {errorText(generate.error)}
        </p>
      )}
      {partial && recoverySummary && (
        <p className="quality-note" role="status">
          本机部分恢复 · 已校验 {recoverySummary.retained_cards} /{" "}
          {recoverySummary.original_cards} 张卡片。
        </p>
      )}
      {earlierPartial && (
        <p className="quality-note">
          当前显示上一次在本机部分恢复的卡片，已校验{" "}
          {earlierPartial.retained_cards} / {earlierPartial.original_cards} 张。
        </p>
      )}
      {(completed || partial || earlierPartial) && cards && (
        <>
          <PaperCardSet
            key={`${displayedResultId}:${cards.source_fingerprint}`}
            data={cards}
            paperId={paperId}
            revisionId={revisionId}
            resultId={displayedResultId ?? ""}
            initialCardId={initialNodeId}
            onOpenSection={source === "local" ? onOpenSection : undefined}
          />
          {data?.cache_hit && (
            <div className="card-set-result-meta">
              <span className="pill">缓存命中 · 新增模型调用 0</span>
            </div>
          )}
        </>
      )}
    </section>
  );
}

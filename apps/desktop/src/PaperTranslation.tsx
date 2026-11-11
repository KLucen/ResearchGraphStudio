import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { invoke } from "@tauri-apps/api/core";
import {
  api,
  request,
  type TranslationInput,
  type TranslationOutputMode,
  type TranslationView,
} from "./api";
import type { GlobalModels } from "./ModelSettings";

const statusLabels: Record<TranslationView["status"], string> = {
  PENDING: "等待翻译",
  RUNNING: "正在翻译",
  COMPLETED: "引擎已生成",
  FAILED: "失败",
  CANCELLED: "已取消",
  INTERRUPTED: "已中断",
};
const stageLabels: Record<string, string> = {
  queued: "等待翻译",
  checking: "核对 PDF 与翻译服务",
  starting_service: "启动翻译引擎",
  stopping_service: "关闭本应用启动的引擎",
  translating: "翻译文本与排版",
  downloading: "保存译文文件",
  completed: "引擎已生成",
  failed: "翻译失败",
  cancelled: "取消翻译",
  interrupted: "任务中断",
};
const active = (value: TranslationView) =>
  ["PENDING", "RUNNING"].includes(value.status);
const outputLabels = {
  dual: "双语对照 PDF",
  mono: "中文 PDF",
  both: "中文与双语 PDF",
};

export function PaperTranslation(props: {
  paperId: string;
  revisionId: string;
  pageCount: number;
  connected: boolean;
}) {
  return (
    <PaperTranslationSession
      key={`${props.paperId}:${props.revisionId}`}
      {...props}
    />
  );
}

function PaperTranslationSession({
  paperId,
  revisionId,
  pageCount,
  connected,
}: {
  paperId: string;
  revisionId: string;
  pageCount: number;
  connected: boolean;
}) {
  const client = useQueryClient();
  const [profileId, setProfileId] = useState("");
  const [outputMode, setOutputMode] = useState<TranslationOutputMode>("dual");
  const [maxCalls, setMaxCalls] = useState(100);
  const [maxInput, setMaxInput] = useState(200000);
  const [consent, setConsent] = useState({
    key: "",
    network: false,
    exclusive: false,
  });
  const settings = useQuery({
    queryKey: ["translation-settings"],
    queryFn: api.translationSettings,
    enabled: connected,
  });
  const models = useQuery({
    queryKey: ["model-settings"],
    queryFn: () => request<GlobalModels>("GET", "/api/v1/settings/models"),
    enabled: connected,
  });
  const selectedProfile =
    profileId ||
    models.data?.roles.reasoning ||
    models.data?.roles.extraction ||
    models.data?.profiles[0]?.id ||
    "";
  const input: TranslationInput = {
    document_version_id: revisionId,
    profile_id: selectedProfile,
    output_mode: outputMode,
    max_calls: maxCalls,
    max_input_tokens: maxInput,
  };
  const launchMode = settings.data?.launch_mode ?? "bundled";
  const configurationKey = JSON.stringify({
    input,
    settings: settings.data,
    settingsUpdatedAt: settings.dataUpdatedAt,
    modelsUpdatedAt: models.dataUpdatedAt,
    profile: models.data?.profiles.find(
      (profile) => profile.id === selectedProfile,
    ),
  });
  const allowNetwork = consent.key === configurationKey && consent.network;
  const exclusive = consent.key === configurationKey && consent.exclusive;
  const resetConsent = () =>
    setConsent({ key: "", network: false, exclusive: false });
  const validInput =
    Boolean(selectedProfile) &&
    Number.isInteger(maxCalls) &&
    maxCalls > 0 &&
    maxCalls <= 2000 &&
    Number.isInteger(maxInput) &&
    maxInput >= 1000 &&
    maxInput <= 5000000;
  const listKey = ["translations", paperId, revisionId];
  const translations = useQuery({
    queryKey: listKey,
    queryFn: () => api.translations(paperId, revisionId),
    enabled: connected,
    refetchInterval: (query) => (query.state.data?.some(active) ? 1500 : false),
  });
  const records = (translations.data ?? []).filter(
    (item) =>
      item.paper_id === paperId && item.document_version_id === revisionId,
  );
  const prepare = useMutation({
    mutationFn: ({
      body,
    }: {
      body: TranslationInput;
      configurationKey: string;
    }) => api.prepareTranslation(paperId, body),
  });
  const preparation =
    prepare.variables?.configurationKey === configurationKey
      ? prepare.data
      : null;
  const create = useMutation({
    mutationFn: () =>
      api.createTranslation(paperId, {
        ...input,
        expected_fingerprint: preparation?.prepare_fingerprint ?? "",
        allow_network: allowNetwork,
        exclusive_service: launchMode === "bundled" || exclusive,
      }),
    onSuccess: () => {
      resetConsent();
      void client.invalidateQueries({ queryKey: listKey });
      void client.invalidateQueries({ queryKey: ["jobs"] });
      void client.invalidateQueries({ queryKey: ["lite-usage"] });
    },
  });
  const cancel = useMutation({
    mutationFn: (id: string) => api.cancelTranslation(paperId, id),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: listKey });
      void client.invalidateQueries({ queryKey: ["jobs"] });
      void client.invalidateQueries({ queryKey: ["lite-usage"] });
    },
  });
  const open = useMutation({
    mutationFn: ({ id, kind }: { id: string; kind: "mono" | "dual" }) =>
      invoke("open_translation_artifact", { translationId: id, kind }),
  });
  const error =
    settings.error ??
    models.error ??
    translations.error ??
    prepare.error ??
    create.error ??
    cancel.error ??
    open.error;
  const canGenerate = Boolean(
    preparation &&
    (preparation.cache_hit ||
      (settings.data?.enabled &&
        preparation.service_ready &&
        preparation.active_tasks === 0 &&
        allowNetwork &&
        (launchMode === "bundled" || exclusive))),
  );
  return (
    <section className="paper-translation" aria-label="文献翻译">
      <div className="translation-heading">
        <div>
          <h3>文献翻译</h3>
          <p className="muted">英文 → 简体中文 · 保留论文排版</p>
        </div>
        <span className="pill">
          {launchMode === "bundled"
            ? "内置翻译引擎"
            : launchMode === "managed"
              ? "外部服务自动启停"
              : "手动连接服务"}
        </span>
      </div>
      <p className="quality-note">
        译文用于辅助阅读，不作为作者原文证据。全文翻译质量与复杂公式、表格的排版尚未验证。
      </p>
      {!settings.data?.enabled && settings.isSuccess && (
        <p className="quality-note">
          文献翻译尚未启用。请到“设置与诊断 → 文献翻译服务”启用。
        </p>
      )}
      <div className="translation-config">
        <label>
          翻译模型
          <select
            value={selectedProfile}
            onChange={(event) => {
              setProfileId(event.target.value);
              resetConsent();
              prepare.reset();
            }}
          >
            <option value="">选择已配置的模型</option>
            {models.data?.profiles
              .filter((profile) => profile.provider !== "mock")
              .map((profile) => (
                <option key={profile.id} value={profile.id}>
                  {profile.name} · {profile.model}
                </option>
              ))}
          </select>
        </label>
        <label>
          输出文件
          <select
            value={outputMode}
            onChange={(event) => {
              setOutputMode(event.target.value as TranslationOutputMode);
              resetConsent();
              prepare.reset();
            }}
          >
            <option value="dual">双语对照 PDF</option>
            <option value="mono">中文 PDF</option>
          </select>
        </label>
        <div className="translation-scope">
          <strong>全文翻译 · {pageCount} 页</strong>
          <p className="muted">当前翻译引擎处理整篇 PDF，暂不提供页码范围。</p>
        </div>
        <label>
          最多模型请求数
          <input
            type="number"
            min={1}
            max={2000}
            value={maxCalls}
            onChange={(event) => {
              setMaxCalls(Number(event.target.value));
              resetConsent();
              prepare.reset();
            }}
          />
        </label>
        <label>
          累计输入估算上限
          <input
            type="number"
            min={1000}
            max={5000000}
            value={maxInput}
            onChange={(event) => {
              setMaxInput(Number(event.target.value));
              resetConsent();
              prepare.reset();
            }}
          />
        </label>
      </div>
      <p className="muted">
        复用已保存的模型连接与密钥。累计输入按请求文本的 UTF-8
        字节保守估算，并非供应商实测 Token 或费用上限。单次请求最多输出 8192
        Token，已知模型上限更低时取低值。
      </p>
      <button
        className="button secondary"
        disabled={
          !connected || !validInput || prepare.isPending || records.some(active)
        }
        onClick={() => {
          resetConsent();
          prepare.mutate({ body: input, configurationKey });
        }}
      >
        {prepare.isPending ? "正在预检…" : "预检范围与预算"}
      </button>
      {preparation && (
        <div className="translation-preflight" role="status">
          <strong>
            {preparation.cache_hit
              ? "已找到匹配缓存，不新增模型调用"
              : "翻译预检"}
          </strong>
          <p>
            PDF 第 {preparation.page_start}–{preparation.page_end} 页 ·{" "}
            {preparation.source_characters.toLocaleString("zh-CN")} 字符 ·
            本地输入估算{" "}
            {preparation.estimated_input_tokens.toLocaleString("zh-CN")} · 输出{" "}
            {outputLabels[preparation.output_mode ?? "both"]}
          </p>
          <p className="muted">{preparation.estimate_note}</p>
          {(preparation.launch_mode ?? launchMode) !== "manual" &&
            !preparation.cache_hit &&
            preparation.service_ready && (
              <p className="muted">
                {(preparation.launch_mode ?? launchMode) === "bundled"
                  ? "内置引擎资源就绪。预检没有启动进程；提交翻译后按需启动，任务结束后自动关闭引擎。"
                  : "启动配置就绪。预检没有启动进程；提交翻译后按需启动，任务结束后自动关闭本应用启动的服务。"}
              </p>
            )}
          {preparation.cache_hit && (
            <p className="muted">读取缓存不会启动翻译引擎或调用模型。</p>
          )}
          <p className="muted">
            模型 {preparation.model_id} · 累计输入估算上限{" "}
            {maxInput.toLocaleString("zh-CN")} · 请求上限 {maxCalls}
          </p>
          {!preparation.service_ready && !preparation.cache_hit && (
            <p className="quality-note">
              翻译引擎尚未就绪，请检查设置后重新预检。
            </p>
          )}
          {preparation.active_tasks > 0 && (
            <p className="quality-note">
              翻译引擎有活动任务，请等待其结束后重新预检。
            </p>
          )}
          {preparation.warnings.map((warning) => (
            <p className="quality-note" key={warning}>
              {warning}
            </p>
          ))}
        </div>
      )}
      <div className="translation-consent">
        <label className="translation-checkbox">
          <input
            type="checkbox"
            checked={allowNetwork}
            onChange={(event) =>
              setConsent({
                key: configurationKey,
                network: event.target.checked,
                exclusive,
              })
            }
          />
          {launchMode === "bundled"
            ? "允许将所选论文的文本发送到上述模型 API 进行翻译。"
            : "允许将所选 PDF 发送到本机翻译服务，并将论文文本发送到上述模型 API。"}
        </label>
        {launchMode !== "bundled" && (
          <label className="translation-checkbox">
            <input
              type="checkbox"
              checked={exclusive}
              onChange={(event) =>
                setConsent({
                  key: configurationKey,
                  network: allowNetwork,
                  exclusive: event.target.checked,
                })
              }
            />
            确认该服务由本应用独占使用，并知晓服务会在自己的目录保留 PDF
            副本和译文。
          </label>
        )}
      </div>
      <div className="translation-actions">
        <button
          className="button primary"
          disabled={
            !connected ||
            !canGenerate ||
            create.isPending ||
            records.some(active)
          }
          onClick={() => create.mutate()}
        >
          {create.isPending
            ? "正在提交…"
            : preparation?.cache_hit
              ? "读取匹配译文缓存"
              : outputMode === "dual"
                ? "生成双语对照 PDF"
                : "生成中文 PDF"}
        </button>
        <span className="muted">
          {launchMode === "bundled"
            ? "PDF 副本与译文保存在本地。取消会阻断后续模型请求并关闭引擎；已发送的请求仍可能计费。"
            : launchMode === "managed"
              ? "取消会阻断后续模型请求，并请求关闭本应用启动的服务；已发送的请求仍可能计费。"
              : "取消可阻断后续模型请求，外部排版过程可能继续；手动启动的服务不会被关闭。"}
        </span>
      </div>
      {error && (
        <p role="alert" className="error-text">
          {error instanceof Error ? error.message : String(error)}
        </p>
      )}
      <div className="translation-results">
        <h4>当前 PDF 修订的译文</h4>
        {translations.isPending && <p role="status">正在读取译文记录…</p>}
        {translations.isSuccess && records.length === 0 && (
          <p className="muted">尚未生成。导入和打开论文不会自动翻译。</p>
        )}
        {records.map((record) => (
          <article className="translation-result" key={record.id}>
            <div className="translation-result-header">
              <strong>{statusLabels[record.status]}</strong>
              <span className="muted">
                PDF 第 {record.page_start}–{record.page_end} 页 ·{" "}
                {record.model_id} · 输出{" "}
                {outputLabels[record.output_mode ?? "both"]}
              </span>
              {record.cache_hit && <span className="pill">缓存</span>}
            </div>
            {active(record) && (
              <>
                <progress
                  aria-label="翻译进度"
                  max={100}
                  value={Math.max(0, Math.min(100, record.progress))}
                />
                <p role="status">
                  {(record.stage && stageLabels[record.stage]) ||
                    "等待翻译服务"}{" "}
                  · {Math.round(record.progress)}%
                </p>
                <button
                  className="button secondary"
                  disabled={!connected || cancel.isPending}
                  onClick={() => cancel.mutate(record.id)}
                >
                  取消翻译
                </button>
              </>
            )}
            {record.status === "CANCELLED" && (
              <p className="muted">
                {record.launch_mode === "bundled"
                  ? "已阻断后续模型请求，并请求关闭内置翻译引擎。已送达供应商的请求仍可能计费。"
                  : record.launch_mode === "managed"
                    ? "已阻断后续模型请求，并请求关闭本应用启动的服务。已送达供应商的请求仍可能计费。"
                    : "已阻断后续模型请求；外部排版可能仍在结束处理中，手动启动的服务不会被关闭。"}
              </p>
            )}
            {record.error && (
              <p className="error-text">
                {record.error_code ? `${record.error_code} · ` : ""}
                {record.error}
              </p>
            )}
            {record.warnings.map((warning) => (
              <p className="quality-note" key={warning}>
                {warning}
              </p>
            ))}
            {record.status === "COMPLETED" && (
              <>
                <p className="muted">
                  引擎已生成文件，全文质量尚未验证。原 PDF 保持不变。
                </p>
                <div className="translation-actions">
                  {record.artifacts.map((artifact) => (
                    <button
                      className="button secondary"
                      key={artifact.kind}
                      disabled={open.isPending}
                      onClick={() =>
                        open.mutate({ id: record.id, kind: artifact.kind })
                      }
                    >
                      {artifact.kind === "mono"
                        ? "打开中文 PDF"
                        : "打开双语 PDF"}
                    </button>
                  ))}
                </div>
              </>
            )}
            <p className="translation-usage">
              模型请求 {record.usage.calls} · 重试 {record.usage.retry_count} ·
              已记录输入 {record.usage.input_tokens.toLocaleString("zh-CN")} /
              输出 {record.usage.output_tokens.toLocaleString("zh-CN")} Token
              {record.usage.unknown_usage_calls > 0
                ? ` · ${record.usage.unknown_usage_calls} 次用量未知，不能按 0 计算`
                : ""}{" "}
              · 费用{" "}
              {record.usage.cost_known && record.usage.cost_estimate !== null
                ? `$${record.usage.cost_estimate}`
                : "unknown"}
            </p>
            <small className="mono">
              源 PDF {record.source_hash.slice(0, 12)} ·{" "}
              {new Date(record.created_at).toLocaleString("zh-CN")}
            </small>
          </article>
        ))}
      </div>
    </section>
  );
}

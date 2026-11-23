import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, LoaderCircle, Pencil, X } from "lucide-react";
import {
  api,
  type ModelDocumentOutput,
  type ModelDocumentParse,
  type ModelDocumentSegment,
  type ModelDocumentSegmentEdit,
  type ChapterProgress,
  type ModelChapterReadingStates,
  type ImportSession,
} from "./api";
import { ReadingOutline } from "./ReadingOutline";
import { ChapterProgressControls } from "./ChapterProgress";
import { ReadingTaskStatus, useModelImportSession } from "./ReadingTaskStatus";
import {
  ReadingFormulaDisplay,
  ReadingLegend,
  ReadingParagraphCard,
  ReadingTableDisplay,
} from "./ReadingContent";
import {
  modelReadingData,
  modelSegmentPageLabel,
} from "./modelDocumentReading";
import { ArgumentSummary } from "./SectionCloseReading";
import { PaperOverview } from "./PaperOverview";

function statusLabel(status: string) {
  const labels: Record<string, string> = {
    queued: "排队中",
    running: "解析中",
    succeeded: "已完成",
    partial: "部分可用",
    failed: "失败",
    interrupted: "已中断",
    cancelled: "已取消",
    paused: "已暂停",
    planned: "已计划",
    degraded: "部分可用",
    needs_review: "待核对",
    unavailable: "不可用",
  };
  return labels[status] ?? status;
}

function ModelOutputFormatRepair({
  sessionId,
  paperId,
  output,
  connected,
}: {
  sessionId: string;
  paperId?: string | null;
  output: ModelDocumentOutput;
  connected: boolean;
}) {
  const [allowNetwork, setAllowNetwork] = useState(false);
  const client = useQueryClient();
  const repair = useMutation({
    mutationFn: () => api.repairModelDocumentOutput(sessionId, output.id),
    retry: false,
    onSuccess: () => {
      setAllowNetwork(false);
      void client.invalidateQueries({
        queryKey: ["model-document-outputs", sessionId],
      });
      void client.invalidateQueries({
        queryKey: ["model-document-import-session", sessionId],
      });
      void client.invalidateQueries({ queryKey: ["jobs"] });
    },
  });
  const localRecovery = useMutation({
    mutationFn: () => {
      if (!paperId) throw new Error("当前输出没有可用的论文标识。");
      return api.recoverModelDocumentOutput(paperId, output.id);
    },
    retry: false,
    onSuccess: () => {
      void client.invalidateQueries({
        queryKey: ["model-document-outputs", sessionId],
      });
      void client.invalidateQueries({
        queryKey: ["model-document-import-session", sessionId],
      });
    },
  });
  const available = output.format_repair_available === true;
  const localRecoveryAvailable =
    output.item_kind === "paper_reading" &&
    output.local_recovery_available === true &&
    Boolean(paperId);
  return (
    <section className="quality-note" aria-label="生成内容校验失败">
      <p>
        {output.item_kind === "paper_reading"
          ? "全文精读"
          : output.item_kind === "translation"
            ? "中文翻译"
            : "论文概览"}
        生成未通过校验：{output.error || output.error_code}
      </p>
      {localRecoveryAvailable && (
        <>
          <p className="muted">
            原始响应已保留。可在本机校验并恢复可验证的精读标记，不会调用模型。
          </p>
          <button
            className="button secondary"
            type="button"
            disabled={localRecovery.isPending || localRecovery.isSuccess}
            onClick={() => localRecovery.mutate()}
          >
            {localRecovery.isPending
              ? "正在本地校验…"
              : "本地恢复可验证的精读标记（不调用模型）"}
          </button>
        </>
      )}
      {localRecovery.error && (
        <p role="alert" className="error-text">
          {localRecovery.error.message}
        </p>
      )}
      {localRecovery.isSuccess && (
        <p role="status">本地恢复结果已保存；原始失败记录保留。</p>
      )}
      {available && (
        <>
          <label className="consent-inline">
            <input
              type="checkbox"
              checked={allowNetwork}
              disabled={repair.isPending || repair.isSuccess}
              onChange={(event) => setAllowNetwork(event.target.checked)}
            />
            允许额外一次模型请求，分析并修复此失败结果的格式（可能产生费用）
          </label>
          <p className="muted">
            只提交本次失败结果、字段错误和必要的原段落，不重新上传
            PDF；修复后仍须完整通过校验。
          </p>
          <button
            className="button secondary"
            type="button"
            disabled={
              !connected ||
              !allowNetwork ||
              repair.isPending ||
              repair.isSuccess
            }
            onClick={() => repair.mutate()}
          >
            {repair.isPending
              ? "正在提交格式修复…"
              : "调用模型分析并修复此结果"}
          </button>
        </>
      )}
      {repair.error && (
        <p role="alert" className="error-text">
          {repair.error.message}
        </p>
      )}
      {repair.isSuccess && (
        <p role="status">格式修复已加入任务记录；原失败记录保留。</p>
      )}
    </section>
  );
}

function ModelBatchFormatRepair({
  sessionId,
  connected,
}: {
  sessionId: string;
  connected: boolean;
}) {
  const [allowNetwork, setAllowNetwork] = useState(false);
  const client = useQueryClient();
  const status = useQuery({
    queryKey: ["model-document-format-repair", sessionId],
    queryFn: () => api.modelDocumentFormatRepair(sessionId),
    enabled: connected,
    retry: false,
  });
  const repair = useMutation({
    mutationFn: () => api.repairModelDocumentBatch(sessionId),
    retry: false,
    onSuccess: () => {
      setAllowNetwork(false);
      void client.invalidateQueries({
        queryKey: ["model-document-format-repair", sessionId],
      });
      void client.invalidateQueries({
        queryKey: ["model-document-import-session", sessionId],
      });
      void client.invalidateQueries({
        queryKey: ["model-document-parse", sessionId],
      });
      void client.invalidateQueries({ queryKey: ["jobs"] });
    },
  });
  if (!status.data?.available && !repair.isSuccess) return null;
  return (
    <section className="quality-note" aria-label="失败批次格式修复">
      <p>
        第 {status.data?.page_start}–{status.data?.page_end}{" "}
        页的模型结果未通过格式校验，已成功的批次保留。
      </p>
      <label className="consent-inline">
        <input
          type="checkbox"
          checked={allowNetwork}
          disabled={repair.isPending || repair.isSuccess}
          onChange={(event) => setAllowNetwork(event.target.checked)}
        />
        允许额外一次模型请求修复本批格式（可能产生费用）
      </label>
      <p className="muted">
        发送已保存的失败响应与契约错误，修复此批；不会重新上传整篇
        PDF，修复后仍须校验。
      </p>
      <button
        className="button secondary"
        type="button"
        disabled={
          !allowNetwork || !connected || repair.isPending || repair.isSuccess
        }
        onClick={() => repair.mutate()}
      >
        {repair.isPending ? "正在提交格式修复…" : "调用模型分析并修复本批格式"}
      </button>
      {repair.error && (
        <p role="alert" className="error-text">
          {repair.error.message}
        </p>
      )}
      {repair.isSuccess && <p role="status">本批格式修复已加入任务记录。</p>}
    </section>
  );
}

function ParseMaterials({
  sessionId,
  parse,
}: {
  sessionId: string;
  parse: ModelDocumentParse;
}) {
  return (
    <div className="model-document-materials">
      <div className="model-document-summary">
        <strong>模型章节解析：{statusLabel(parse.status)}</strong>
        <span>{parse.segments.length} 个章节材料</span>
        {parse.warnings.length > 0 && (
          <span>有 {parse.warnings.length} 条降级提示</span>
        )}
      </div>
      {parse.error && (
        <p role="alert" className="error-text">
          {parse.error}
        </p>
      )}
      <div className="model-document-segments">
        {parse.segments.map((segment) => (
          <SegmentCard
            key={segment.id}
            sessionId={sessionId}
            segment={segment}
          />
        ))}
      </div>
    </div>
  );
}

function SegmentCard({
  sessionId,
  segment,
}: {
  sessionId: string;
  segment: ModelDocumentSegment;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(segment);
  const [tableJsonDraft, setTableJsonDraft] = useState(() =>
    JSON.stringify(segment.table_data ?? null, null, 2),
  );
  const [editorError, setEditorError] = useState("");
  const client = useQueryClient();
  const update = useMutation({
    mutationFn: (values: ModelDocumentSegmentEdit) =>
      api.updateModelDocumentSegment(sessionId, segment.id, values),
    onSuccess: () => {
      void client.invalidateQueries({
        queryKey: ["model-document-parse", sessionId],
      });
      void client.invalidateQueries({
        queryKey: ["model-document-outputs", sessionId],
      });
      void client.invalidateQueries({ queryKey: ["model-overview"] });
      setEditing(false);
      setEditorError("");
    },
  });
  const cancel = () => {
    setDraft(segment);
    setTableJsonDraft(JSON.stringify(segment.table_data ?? null, null, 2));
    setEditing(false);
    setEditorError("");
    update.reset();
  };
  const save = () => {
    let tableData = draft.table_data;
    if (segment.kind === "table") {
      try {
        const parsed: unknown = tableJsonDraft.trim()
          ? JSON.parse(tableJsonDraft)
          : null;
        if (
          parsed !== null &&
          (typeof parsed !== "object" || Array.isArray(parsed))
        ) {
          throw new Error("invalid table data");
        }
        tableData = parsed as Record<string, unknown> | null;
      } catch {
        setEditorError("结构化表格必须是有效的 JSON 对象或 null。");
        return;
      }
    }
    setEditorError("");
    update.mutate({
      text: draft.text,
      latex: draft.latex,
      mathml: draft.mathml,
      raw_table_text: draft.raw_table_text,
      table_data: tableData,
    });
  };
  return (
    <article className="model-document-segment">
      <header>
        <strong>{segment.chapter_title || segment.chapter_ref}</strong>
        <span>
          {(
            {
              paragraph: "正文段落",
              formula: "公式",
              table: "表格",
              figure: "图片",
              caption: "图表说明",
            } as Record<string, string>
          )[segment.kind] ?? "材料"}
        </span>
        {segment.status !== "ok" && <em>{statusLabel(segment.status)}</em>}
        {!editing ? (
          <button
            type="button"
            className="icon-button model-document-edit"
            aria-label={`编辑${segment.kind}内容`}
            title="编辑解析内容"
            onClick={() => {
              setDraft(segment);
              setTableJsonDraft(
                JSON.stringify(segment.table_data ?? null, null, 2),
              );
              setEditorError("");
              update.reset();
              setEditing(true);
            }}
          >
            <Pencil size={14} />
          </button>
        ) : (
          <div className="model-document-edit-actions">
            <button
              type="button"
              className="icon-button"
              aria-label="保存解析内容"
              title="保存"
              disabled={update.isPending}
              onClick={save}
            >
              {update.isPending ? (
                <LoaderCircle size={14} className="spin" />
              ) : (
                <Check size={14} />
              )}
            </button>
            <button
              type="button"
              className="icon-button"
              aria-label="取消编辑解析内容"
              title="取消"
              disabled={update.isPending}
              onClick={cancel}
            >
              <X size={14} />
            </button>
          </div>
        )}
      </header>
      {update.isError && (
        <p role="alert" className="error-text">
          {update.error.message}
        </p>
      )}
      {editorError && (
        <p role="alert" className="error-text">
          {editorError}
        </p>
      )}
      {editing ? (
        <div className="model-document-segment-editor">
          <label>
            原文/说明
            <textarea
              value={draft.text ?? ""}
              onChange={(event) =>
                setDraft((current) => ({
                  ...current,
                  text: event.target.value || null,
                }))
              }
            />
          </label>
          {(segment.kind === "formula" || draft.latex || draft.mathml) && (
            <>
              <label>
                LaTeX
                <textarea
                  value={draft.latex ?? ""}
                  onChange={(event) =>
                    setDraft((current) => ({
                      ...current,
                      latex: event.target.value || null,
                    }))
                  }
                />
              </label>
              <label>
                MathML
                <textarea
                  value={draft.mathml ?? ""}
                  onChange={(event) =>
                    setDraft((current) => ({
                      ...current,
                      mathml: event.target.value || null,
                    }))
                  }
                />
              </label>
            </>
          )}
          {segment.kind === "table" && (
            <>
              <label>
                表格文本
                <textarea
                  value={draft.raw_table_text ?? ""}
                  onChange={(event) =>
                    setDraft((current) => ({
                      ...current,
                      raw_table_text: event.target.value || null,
                    }))
                  }
                />
              </label>
              <label>
                结构化表格 JSON
                <textarea
                  value={tableJsonDraft}
                  onChange={(event) => setTableJsonDraft(event.target.value)}
                />
              </label>
            </>
          )}
        </div>
      ) : (
        <>
          {segment.text && <p>{segment.text}</p>}
          {segment.kind === "formula" && (
            <ReadingFormulaDisplay
              latex={segment.latex}
              status={segment.status}
              source={segment.text || segment.mathml || ""}
              unverified
            />
          )}
          {segment.mathml && !segment.latex && (
            <pre className="model-document-formula">{segment.mathml}</pre>
          )}
          {segment.kind === "table" && (
            <ReadingTableDisplay
              data={segment.table_data}
              rawText={segment.raw_table_text || segment.text}
            />
          )}
        </>
      )}
    </article>
  );
}

function OutputCard({
  sessionId,
  output,
}: {
  sessionId: string;
  output: ModelDocumentOutput;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(output.output_json);
  const client = useQueryClient();
  const update = useMutation({
    mutationFn: () =>
      api.updateModelDocumentOutput(sessionId, output.id, draft ?? {}),
    onSuccess: () => {
      void client.invalidateQueries({
        queryKey: ["model-document-outputs", sessionId],
      });
      setEditing(false);
    },
  });
  const data = output.output_json;
  const label =
    output.item_kind === "paper_overview"
      ? "论文概览"
      : output.item_kind === "paper_reading"
        ? "全文精读"
        : "逐段中文翻译";
  return (
    <article className="model-document-output">
      <header>
        <strong>{label}</strong>
        <span>{statusLabel(output.status)}</span>
        {data && output.status === "succeeded" && !editing && (
          <button
            type="button"
            className="icon-button model-document-edit"
            aria-label={`编辑${label}内容`}
            title="编辑生成内容"
            onClick={() => {
              setDraft(data);
              setEditing(true);
            }}
          >
            <Pencil size={14} />
          </button>
        )}
        {editing && (
          <div className="model-document-edit-actions">
            <button
              type="button"
              className="icon-button"
              aria-label="保存生成内容"
              title="保存"
              disabled={update.isPending}
              onClick={() => update.mutate()}
            >
              {update.isPending ? (
                <LoaderCircle size={14} className="spin" />
              ) : (
                <Check size={14} />
              )}
            </button>
            <button
              type="button"
              className="icon-button"
              aria-label="取消编辑生成内容"
              title="取消"
              disabled={update.isPending}
              onClick={() => {
                setDraft(data);
                setEditing(false);
                update.reset();
              }}
            >
              <X size={14} />
            </button>
          </div>
        )}
      </header>
      {output.error && <p className="error-text">{output.error}</p>}
      {update.isError && (
        <p role="alert" className="error-text">
          {update.error.message}
        </p>
      )}
      {editing && draft ? (
        <div className="model-document-output-editor">
          <label>
            摘要
            <textarea
              value={draft.summary ?? ""}
              onChange={(event) =>
                setDraft((current) =>
                  current
                    ? { ...current, summary: event.target.value }
                    : current,
                )
              }
            />
          </label>
          {draft.sections?.map((section, index) => (
            <label key={`${output.id}-${section.chapter_ref}`}>
              {section.chapter_ref} · 章节内容
              <textarea
                value={section.text}
                onChange={(event) =>
                  setDraft((current) =>
                    current
                      ? {
                          ...current,
                          sections: current.sections?.map((item, itemIndex) =>
                            itemIndex === index
                              ? { ...item, text: event.target.value }
                              : item,
                          ),
                        }
                      : current,
                  )
                }
              />
            </label>
          ))}
          {draft.translations?.map((translation, index) => (
            <label key={`${output.id}-translation-${index}`}>
              {translation.chapter_ref} · 中文翻译
              <textarea
                value={translation.translation_zh}
                onChange={(event) =>
                  setDraft((current) =>
                    current
                      ? {
                          ...current,
                          translations: current.translations?.map(
                            (item, itemIndex) =>
                              itemIndex === index
                                ? {
                                    ...item,
                                    translation_zh: event.target.value,
                                  }
                                : item,
                          ),
                        }
                      : current,
                  )
                }
              />
            </label>
          ))}
          {(["contributions", "findings", "limitations"] as const).map(
            (key) => (
              <label key={key}>
                {key === "contributions"
                  ? "贡献"
                  : key === "findings"
                    ? "发现"
                    : "局限"}
                <textarea
                  value={(draft[key] ?? []).join("\n")}
                  onChange={(event) =>
                    setDraft((current) =>
                      current
                        ? {
                            ...current,
                            [key]: event.target.value
                              .split("\n")
                              .filter((line) => line.trim()),
                          }
                        : current,
                    )
                  }
                />
              </label>
            ),
          )}
        </div>
      ) : (
        <>
          {data?.summary && <p>{data.summary}</p>}
          {data?.sections?.map((section) => (
            <section key={`${output.id}-${section.chapter_ref}`}>
              <h4>{section.chapter_ref}</h4>
              <p>{section.text}</p>
            </section>
          ))}
          {data?.translations?.map((translation, index) => (
            <section key={`${output.id}-translation-${index}`}>
              <p>{translation.source_text}</p>
              <p className="muted">{translation.translation_zh}</p>
            </section>
          ))}
          {data?.contributions?.map((value, index) => (
            <p key={`contribution-${index}`}>{value}</p>
          ))}
          {data?.findings?.map((value, index) => (
            <p key={`finding-${index}`}>{value}</p>
          ))}
          {data?.limitations?.map((value, index) => (
            <p key={`limitation-${index}`}>{value}</p>
          ))}
        </>
      )}
    </article>
  );
}

function ModelFullReading({
  sessionId,
  connected,
  parse,
  outputs,
  session,
}: {
  sessionId: string;
  connected: boolean;
  parse: ModelDocumentParse;
  outputs: ModelDocumentOutput[];
  session?: ImportSession;
}) {
  const [allowNetwork, setAllowNetwork] = useState(false);
  const [includeTranslation, setIncludeTranslation] = useState(false);
  const chapters = [
    ...new Map(
      [...parse.segments]
        .sort(
          (a, b) => a.chapter_order - b.chapter_order || a.ordinal - b.ordinal,
        )
        .map((segment) => [segment.chapter_ref, segment] as const),
    ).values(),
  ];
  const minLevel = Math.min(
    ...chapters.map((chapter) => chapter.chapter_level),
  );
  let rootRef = "";
  const chapterRoot = new Map<string, string>();
  for (const chapter of chapters) {
    if (chapter.chapter_level === minLevel) rootRef = chapter.chapter_ref;
    chapterRoot.set(chapter.chapter_ref, rootRef);
  }
  const roots = chapters.filter(
    (chapter) => chapter.chapter_level === minLevel,
  );
  const stateKey = ["model-chapter-reading-states", sessionId, parse.id];
  const client = useQueryClient();
  const generate = useMutation({
    mutationFn: () =>
      api.generateModelDocumentOutput(sessionId, "paper_reading", {
        allow_network: true,
        translation_mode: includeTranslation ? "full" : "none",
        force_regenerate: true,
      }),
    retry: false,
    onSuccess: () => {
      setAllowNetwork(false);
      void client.invalidateQueries({
        queryKey: ["model-document-outputs", sessionId],
      });
      void client.invalidateQueries({
        queryKey: ["model-document-import-session", sessionId],
      });
      void client.invalidateQueries({ queryKey: ["jobs"] });
    },
  });
  const translate = useMutation({
    mutationFn: () =>
      api.generateModelDocumentOutput(sessionId, "translation", {
        allow_network: true,
        translation_mode: "full",
        force_regenerate: true,
      }),
    retry: false,
    onSuccess: () => {
      setAllowNetwork(false);
      void client.invalidateQueries({
        queryKey: ["model-document-outputs", sessionId],
      });
      void client.invalidateQueries({
        queryKey: ["model-document-import-session", sessionId],
      });
      void client.invalidateQueries({ queryKey: ["jobs"] });
    },
  });
  const states = useQuery({
    queryKey: stateKey,
    queryFn: () => api.modelChapterReadingStates(sessionId),
    enabled: connected && parse.status === "succeeded",
    retry: false,
  });
  const currentStates =
    states.data?.parse_id === parse.id ? states.data.items : [];
  const progressOf = (chapterRef: string): ChapterProgress =>
    currentStates.find((item) => item.chapter_ref === chapterRef)?.progress ??
    "NOT_STARTED";
  const save = useMutation({
    mutationFn: ({
      chapter_ref,
      progress,
    }: {
      chapter_ref: string;
      progress: ChapterProgress;
    }) =>
      api.saveModelChapterReadingState(sessionId, {
        parse_id: parse.id,
        chapter_ref,
        progress,
      }),
    retry: false,
    onSuccess: (value) => {
      if (value.parse_id !== parse.id) return;
      client.setQueryData<ModelChapterReadingStates>(stateKey, (previous) => ({
        parse_id: value.parse_id,
        items: [
          ...(previous?.parse_id === value.parse_id
            ? previous.items
            : []
          ).filter((item) => item.chapter_ref !== value.chapter_ref),
          {
            chapter_ref: value.chapter_ref,
            progress: value.progress,
            updated_at: value.updated_at,
          },
        ],
      }));
    },
  });
  const data = modelReadingData(parse, outputs);
  const pending =
    generate.isPending ||
    translate.isPending ||
    session?.items.some(
      (item) =>
        ["paper_reading", "translation"].includes(item.item_kind) &&
        ["queued", "running"].includes(item.status),
    ) ||
    outputs.some((output) =>
      ["pending", "queued", "running"].includes(output.status),
    );
  const renderSegment = (segment: ModelDocumentSegment) =>
    segment.kind === "paragraph" ? (
      <ReadingParagraphCard
        key={segment.id}
        id={segment.id}
        elementId={`model-reading-paragraph-${segment.id}`}
        text={segment.text || ""}
        paragraphNumber={data.numbers.get(segment.id) ?? 0}
        metadata={modelSegmentPageLabel(segment)}
        analysis={data.analyses.get(segment.id)}
        translation={data.translations.get(segment.id)}
        translationUnavailableMessage="尚无本段译文。可在上方选择逐段中文翻译。"
        sourceDetails={
          <details className="paper-reading-source-map">
            <summary>模型提取来源与定位</summary>
            <p>此正文来自模型提取稿，请对照原始论文核验。</p>
            <p>{modelSegmentPageLabel(segment)}</p>
            <p className="mono">段落标识：{segment.id}</p>
            {segment.status !== "ok" && (
              <p className="quality-note">
                此材料需要核对：{statusLabel(segment.status)}
              </p>
            )}
            {segment.warnings.map((warning, index) => (
              <p key={index}>{warning}</p>
            ))}
          </details>
        }
      />
    ) : (
      <SegmentCard key={segment.id} sessionId={sessionId} segment={segment} />
    );
  const targetId = (chapterRef: string) =>
    `model-reading-${parse.id}-${chapterRef}`;
  const generationControls = (
    <div className="paper-reading-actions">
      <label className="consent-inline">
        <input
          type="checkbox"
          checked={allowNetwork}
          disabled={pending}
          onChange={(event) => setAllowNetwork(event.target.checked)}
        />
        允许本次发送模型提取内容，生成精读或中文译文（可能产生费用）
      </label>
      <label className="consent-inline">
        <input
          type="checkbox"
          checked={includeTranslation}
          disabled={pending}
          onChange={(event) => setIncludeTranslation(event.target.checked)}
        />
        同时生成逐段中文翻译
      </label>
      <button
        type="button"
        className="button primary"
        disabled={
          !connected ||
          parse.status !== "succeeded" ||
          !allowNetwork ||
          pending ||
          !data.numbers.size
        }
        onClick={() => generate.mutate()}
      >
        {data.reading || data.legacy.length
          ? "重新生成全文精读笔记"
          : "生成全文精读笔记"}
      </button>
      {data.reading && !data.translations.size && (
        <button
          type="button"
          className="button secondary"
          disabled={
            !connected ||
            parse.status !== "succeeded" ||
            !allowNetwork ||
            pending
          }
          onClick={() => translate.mutate()}
        >
          仅补生成中文译文
        </button>
      )}
      <p className="muted">
        只发送已保存的模型提取稿。精读与翻译按各自契约校验后显示；生成不会重新上传整篇
        PDF。精读使用1次模型请求，选择中文翻译另排1次翻译请求；仅补译文只排翻译任务。
      </p>
    </div>
  );
  return (
    <section className="paper-close-reading" aria-label="全文精读">
      <h3>全文精读</h3>
      <p className="muted">
        按章节阅读模型提取的原文、公式与表格，在大章节下记录阅读状态。阅读标记保存在本机，不调用模型。
      </p>
      {!data.reading && !pending && (
        <p className="quality-note">尚无全文精读笔记，可在下方选择生成。</p>
      )}
      {data.readingOutput?.status === "partial" && (
        <p role="status" className="quality-note">
          精读标记部分可用：
          {data.readingOutput.recovery_summary ? (
            <>
              已隐藏
              {data.readingOutput.recovery_summary.unresolved_highlights}
              处引文不匹配的标记；
            </>
          ) : (
            <>仅显示通过校验的标记；</>
          )}
          当前显示的标记已通过本地来源校验。原始响应保留，未调用模型。
          {!!data.readingOutput.recovery_summary?.normalized_types && (
            <>
              {" "}
              另有
              {data.readingOutput.recovery_summary.normalized_types}
              处标记类型已按契约规范化。
            </>
          )}
        </p>
      )}
      {!!data.legacy.length && (
        <p className="quality-note">
          旧版章节摘要已保留，不能直接转换为逐段译文或论证高亮；重新生成后使用统一精读格式。
        </p>
      )}
      {data.readingOutput?.status === "succeeded" ? (
        <details
          className="reading-secondary-actions"
          onToggle={(event) => {
            if (!event.currentTarget.open) setAllowNetwork(false);
          }}
        >
          <summary>更多精读操作</summary>
          {generationControls}
        </details>
      ) : (
        generationControls
      )}
      {generate.error && (
        <p role="alert" className="error-text">
          {generate.error.message}
        </p>
      )}
      {translate.error && (
        <p role="alert" className="error-text">
          {translate.error.message}
        </p>
      )}
      <ReadingLegend />
      {(states.error || save.error) && (
        <p role="alert" className="error-text">
          {(save.error ?? states.error)?.message}
        </p>
      )}
      <ReadingOutline
        entries={chapters.map((chapter) => ({
          id: chapter.chapter_ref,
          label: chapter.chapter_title || chapter.chapter_ref,
          targetId: targetId(chapter.chapter_ref),
          level: chapter.chapter_level,
          ...(chapterRoot.get(chapter.chapter_ref) === chapter.chapter_ref
            ? { progress: progressOf(chapter.chapter_ref) }
            : {}),
        }))}
        trackScroll
      >
        {!!data.numbers.size && (
          <div className="paper-reading-column-labels" aria-hidden="true">
            <span>正文与常驻中文译文</span>
            <span>标记与整段批注</span>
          </div>
        )}
        {chapters
          .filter((chapter) => !chapterRoot.get(chapter.chapter_ref))
          .map((chapter) => (
            <section key={chapter.chapter_ref}>
              <h4
                id={targetId(chapter.chapter_ref)}
                tabIndex={-1}
                className="reading-outline-section"
              >
                {chapter.chapter_title || chapter.chapter_ref}
              </h4>
              {parse.segments
                .filter(
                  (segment) => segment.chapter_ref === chapter.chapter_ref,
                )
                .map(renderSegment)}
            </section>
          ))}
        {roots.map((root) => (
          <section key={root.chapter_ref} className="model-reading-chapter">
            <header
              id={targetId(root.chapter_ref)}
              tabIndex={-1}
              className="reading-outline-section"
              data-reading-anchor
            >
              <h3>{root.chapter_title || root.chapter_ref}</h3>
            </header>
            {chapters
              .filter(
                (chapter) =>
                  chapterRoot.get(chapter.chapter_ref) === root.chapter_ref,
              )
              .map((chapter) => (
                <section key={chapter.chapter_ref}>
                  {chapter.chapter_ref !== root.chapter_ref && (
                    <h4
                      id={targetId(chapter.chapter_ref)}
                      tabIndex={-1}
                      className="reading-outline-section"
                      data-reading-anchor
                    >
                      {chapter.chapter_title || chapter.chapter_ref}
                    </h4>
                  )}
                  {parse.segments
                    .filter(
                      (segment) => segment.chapter_ref === chapter.chapter_ref,
                    )
                    .sort((a, b) => a.ordinal - b.ordinal)
                    .map(renderSegment)}
                </section>
              ))}
            <ChapterProgressControls
              title={root.chapter_title || root.chapter_ref}
              progress={progressOf(root.chapter_ref)}
              disabled={
                !connected ||
                !states.isSuccess ||
                states.data.parse_id !== parse.id ||
                save.isPending
              }
              onChange={(progress) =>
                save.mutate({ chapter_ref: root.chapter_ref, progress })
              }
            />
          </section>
        ))}
        {!chapters.length && (
          <p className="quality-note">模型尚未发布可阅读的章节内容。</p>
        )}
        {data.reading?.paper_argument && (
          <ArgumentSummary
            argument={data.reading.paper_argument}
            label="全文论证结构"
          />
        )}
        {!!outputs.length && (
          <details className="model-document-source">
            <summary>查看全文摘要与管理生成内容</summary>
            {data.legacy.map((output) => (
              <OutputCard
                key={output.id}
                sessionId={sessionId}
                output={output}
              />
            ))}
          </details>
        )}
      </ReadingOutline>
    </section>
  );
}

export function ModelDocumentPanel({
  sessionId,
  connected,
  activeView,
  sessionStatus,
  sessionError,
  paperId,
  showTaskStatus = true,
}: {
  sessionId: string;
  connected: boolean;
  activeView: "overview" | "reading" | "materials";
  sessionStatus: string;
  sessionError: string | null;
  paperId?: string;
  showTaskStatus?: boolean;
}) {
  const client = useQueryClient();
  const [readingMaterialsOpen, setReadingMaterialsOpen] = useState(false);
  const session = useModelImportSession(sessionId, connected);
  const parseJobId = session.data?.items.find(
    (item) => item.item_kind === "document_parse",
  )?.job_id;
  const parseJob = useQuery({
    queryKey: ["job", parseJobId],
    queryFn: () => api.job(parseJobId!),
    enabled: connected && !!parseJobId,
    retry: false,
    refetchInterval: (query) =>
      query.state.data &&
      ["succeeded", "failed", "interrupted", "cancelled"].includes(
        query.state.data.status,
      )
        ? false
        : 1500,
  });
  const parse = useQuery({
    queryKey: ["model-document-parse", sessionId],
    queryFn: () => api.modelDocumentParse(sessionId),
    enabled: connected && !!sessionId,
    refetchInterval: (query) =>
      query.state.data && query.state.data.status === "succeeded"
        ? false
        : 1500,
  });
  const outputs = useQuery({
    queryKey: ["model-document-outputs", sessionId],
    queryFn: () => api.modelDocumentOutputs(sessionId),
    enabled: connected && !!sessionId,
    refetchInterval: 1500,
  });
  const parseItem = session.data?.items.find(
    (item) => item.item_kind === "document_parse",
  );
  const retry = useMutation({
    mutationFn: () => api.retryImportItem(sessionId, "document_parse"),
    retry: false,
    onSuccess: (value) => {
      client.setQueryData(["model-document-import-session", sessionId], value);
      void client.invalidateQueries({
        queryKey: ["model-document-parse", sessionId],
      });
      void client.invalidateQueries({ queryKey: ["job", parseJobId] });
      void client.invalidateQueries({ queryKey: ["jobs"] });
    },
  });
  const active =
    parseItem?.status === "queued" ||
    ["queued", "running"].includes(
      parseJob.data?.status ?? parseItem?.status ?? "",
    );
  const failed =
    !active &&
    (["failed", "interrupted", "paused"].includes(parse.data?.status ?? "") ||
      ["failed", "interrupted", "cancelled", "paused"].includes(
        parseJob.data?.status ?? "",
      ) ||
      ["failed", "interrupted", "paused"].includes(parseItem?.status ?? ""));
  const displayStatus =
    (parseItem?.status === "queued" ? "queued" : parseJob.data?.status) ??
    parseItem?.status ??
    parse.data?.status ??
    session.data?.status ??
    sessionStatus;
  const failureError =
    parseJob.data?.error ||
    parse.data?.error ||
    parseItem?.error ||
    session.data?.error ||
    sessionError;
  const taskStatus = showTaskStatus && (
    <ReadingTaskStatus
      connected={connected}
      session={session.data}
      parseJob={parseJob.data}
    />
  );
  const requestMetadata = parseJob.data?.result?.document_request;
  const batchMetadata = parseJob.data?.result?.document_batches;
  const boundaryRejected =
    !!requestMetadata &&
    typeof requestMetadata === "object" &&
    !Array.isArray(requestMetadata) &&
    (requestMetadata as Record<string, unknown>).http_status === 400 &&
    !!batchMetadata &&
    typeof batchMetadata === "object" &&
    !Array.isArray(batchMetadata) &&
    (batchMetadata as Record<string, unknown>).current_kind === "boundary";
  const boundaryCompatibilityRetry =
    boundaryRejected &&
    (batchMetadata as Record<string, unknown>).compatibility_retry_available ===
      true;
  const publicationRetryAvailable =
    !!batchMetadata &&
    typeof batchMetadata === "object" &&
    !Array.isArray(batchMetadata) &&
    (batchMetadata as Record<string, unknown>).publication_retry_available ===
      true;
  const publicationFailed =
    !!batchMetadata &&
    typeof batchMetadata === "object" &&
    !Array.isArray(batchMetadata) &&
    (batchMetadata as Record<string, unknown>).phase === "publication_failed";
  const retryControl = failed ? (
    <div className="quality-note" role="status">
      {publicationRetryAvailable || publicationFailed ? (
        <>
          <p>
            章节发布未完成，已校验批次保留。
            {publicationRetryAvailable
              ? "本次只重新发布章节，不重发已校验批次，也不重新上传 PDF。"
              : "当前任务已无可用的仅发布恢复，请保留任务记录和已校验检查点，以便检查数据库发布问题。"}
          </p>
          {publicationRetryAvailable && (
            <>
              <p>
                原计划选中的概览或精读任务仍会继续，可能产生模型请求和费用。
              </p>
              <button
                type="button"
                className="button secondary"
                disabled={retry.isPending || !connected}
                onClick={() => retry.mutate()}
              >
                {retry.isPending
                  ? "正在重新排队…"
                  : "仅重新发布章节（不重发批次）"}
              </button>
            </>
          )}
        </>
      ) : session.data?.plan.allow_network ? (
        <>
          {boundaryRejected && (
            <p>
              相同 HTTP 400
              请先停止重复点击。安装修复版后只继续边界复核，保留已完成的正文批次。
              {boundaryCompatibilityRetry
                ? "当前任务可确认使用修复版继续边界复核，可能产生额外模型费用。"
                : "当前任务没有可用的修复版续接，请先检查请求参数或更新软件。"}
            </p>
          )}
          <p>
            本次模型解析没有完成。重试沿用原任务配置，可能产生模型用量；修改模型能力或解析模型后，请使用上方“使用模型重新解析”，按当前配置创建新任务。也可选择本地解析。
          </p>
          <p>
            对分批任务，只继续未成功的批次，已成功检查点保留。若某次请求已发送但结果不确定，点击重试表示确认继续该未完成请求，可能再次产生费用；系统不会自动重发。
          </p>
          {(!boundaryRejected || boundaryCompatibilityRetry) && (
            <button
              type="button"
              className="button secondary"
              disabled={retry.isPending || !connected}
              onClick={() => retry.mutate()}
            >
              {retry.isPending
                ? "正在重新排队…"
                : boundaryCompatibilityRetry
                  ? "确认继续边界复核（可能收费）"
                  : "重试模型解析"}
            </button>
          )}
        </>
      ) : (
        <p>
          当前导入计划没有联网授权。可使用上方“使用模型重新解析”确认当前配置及发送授权，或选择本地解析。
        </p>
      )}
      {retry.error && (
        <p role="alert" className="error-text">
          {retry.error.message}
        </p>
      )}
      <ModelBatchFormatRepair sessionId={sessionId} connected={connected} />
    </div>
  ) : null;
  if (parse.isPending) {
    return (
      <div className="model-document-panel">
        {taskStatus}
        {!active && <p role="status">正在读取模型解析内容…</p>}
      </div>
    );
  }
  if (parse.isError) {
    return (
      <div className="model-document-panel">
        {taskStatus}
        {!active && (
          <>
            <p className="error-text">
              {failureError || "模型章节解析尚未发布。"}
            </p>
            {retryControl}
          </>
        )}
      </div>
    );
  }
  const outputKinds =
    activeView === "overview"
      ? ["paper_overview"]
      : activeView === "reading"
        ? ["paper_reading", "translation"]
        : [];
  const currentOutputs = (outputs.data ?? []).filter(
    (output) => output.parse_id === parse.data.id,
  );
  const visibleOutputs = currentOutputs.filter((output) =>
    outputKinds.includes(output.item_kind),
  );
  const displayedParse = {
    ...parse.data,
    status: displayStatus,
    error: failed ? failureError : parse.data.error,
  };
  const modelPaperId = session.data?.source_snapshot.paper_id ?? paperId;
  return (
    <section className="model-document-panel" aria-label="模型文档解析结果">
      {taskStatus}
      {failed && failureError && activeView !== "materials" && (
        <p role="alert" className="error-text">
          {failureError}
        </p>
      )}
      {retryControl}
      {activeView === "reading" &&
        currentOutputs
          .filter(
            (output) =>
              output.status === "failed" &&
              ["paper_reading", "translation"].includes(output.item_kind),
          )
          .map((output) => (
            <ModelOutputFormatRepair
              key={output.id}
              sessionId={sessionId}
              paperId={modelPaperId}
              output={output}
              connected={connected}
            />
          ))}
      {activeView === "materials" ? (
        <ParseMaterials sessionId={sessionId} parse={displayedParse} />
      ) : activeView === "reading" ? (
        <>
          <ModelFullReading
            sessionId={sessionId}
            connected={connected}
            parse={parse.data}
            outputs={visibleOutputs}
            session={session.data}
          />
          <details
            className="model-document-source"
            open={readingMaterialsOpen}
            onToggle={(event) =>
              setReadingMaterialsOpen(event.currentTarget.open)
            }
          >
            <summary>查看/编辑本次模型解析章节材料</summary>
            {readingMaterialsOpen && (
              <ParseMaterials sessionId={sessionId} parse={parse.data} />
            )}
          </details>
        </>
      ) : (
        <>
          {modelPaperId && session.data && (
            <PaperOverview
              paperId={modelPaperId}
              revisionId={parse.data.id}
              projectId={session.data.project_id}
              source="model"
              connected={connected}
              showActiveTask={false}
            />
          )}
          {!modelPaperId && visibleOutputs.length === 0 && (
            <p className="quality-note">当前解析记录尚无可用的论文卡片集。</p>
          )}
          <details className="model-document-source">
            <summary>查看本次模型解析章节材料</summary>
            <ParseMaterials sessionId={sessionId} parse={parse.data} />
          </details>
        </>
      )}
    </section>
  );
}

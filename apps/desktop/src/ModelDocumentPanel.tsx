import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, LoaderCircle, Pencil, X } from "lucide-react";
import {
  api,
  type ModelDocumentOutput,
  type ModelDocumentParse,
  type ModelDocumentSegment,
  type ModelDocumentSegmentEdit,
} from "./api";

function statusLabel(status: string) {
  const labels: Record<string, string> = {
    queued: "排队中",
    running: "解析中",
    succeeded: "已完成",
    failed: "失败",
    paused: "已暂停",
    planned: "已计划",
  };
  return labels[status] ?? status;
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
        <span>{segment.kind}</span>
        {segment.status !== "ok" && <em>{segment.status}</em>}
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
          {segment.latex && (
            <pre className="model-document-formula">{segment.latex}</pre>
          )}
          {segment.mathml && !segment.latex && (
            <pre className="model-document-formula">{segment.mathml}</pre>
          )}
          {segment.raw_table_text && (
            <pre className="model-document-table">{segment.raw_table_text}</pre>
          )}
          {segment.table_data && (
            <pre className="model-document-table">
              {JSON.stringify(segment.table_data, null, 2)}
            </pre>
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

export function ModelDocumentPanel({
  sessionId,
  connected,
  activeView,
  sessionStatus,
  sessionError,
}: {
  sessionId: string;
  connected: boolean;
  activeView: "overview" | "reading" | "materials";
  sessionStatus: string;
  sessionError: string | null;
}) {
  const parse = useQuery({
    queryKey: ["model-document-parse", sessionId],
    queryFn: () => api.modelDocumentParse(sessionId),
    enabled: connected && !!sessionId,
    refetchInterval: (query) =>
      query.state.data &&
      ["succeeded", "failed", "paused"].includes(query.state.data.status)
        ? false
        : 1500,
  });
  const outputs = useQuery({
    queryKey: ["model-document-outputs", sessionId],
    queryFn: () => api.modelDocumentOutputs(sessionId),
    enabled: connected && !!sessionId,
    refetchInterval: 1500,
  });
  if (parse.isPending) {
    return (
      <div className="model-document-panel" role="status">
        正在加载模型解析结果 · {statusLabel(sessionStatus)}
        {sessionError && <p className="error-text">{sessionError}</p>}
      </div>
    );
  }
  if (parse.isError) {
    return (
      <div className="model-document-panel" role="status">
        <strong>模型章节解析：{statusLabel(sessionStatus)}</strong>
        <p className="error-text">{sessionError || "模型章节解析尚未发布。"}</p>
      </div>
    );
  }
  const outputKinds =
    activeView === "overview"
      ? ["paper_overview"]
      : activeView === "reading"
        ? ["paper_reading", "translation"]
        : [];
  const visibleOutputs = (outputs.data ?? []).filter((output) =>
    outputKinds.includes(output.item_kind),
  );
  return (
    <section className="model-document-panel" aria-label="模型文档解析结果">
      {activeView === "materials" ? (
        <ParseMaterials sessionId={sessionId} parse={parse.data} />
      ) : (
        <>
          {visibleOutputs.map((output) => (
            <OutputCard key={output.id} sessionId={sessionId} output={output} />
          ))}
          {visibleOutputs.length === 0 && (
            <p className="quality-note">
              {activeView === "overview"
                ? "此导入计划没有生成论文概览。"
                : "此导入计划没有生成论文精读或中文翻译。"}
            </p>
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

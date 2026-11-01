import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  api,
  type KnowledgeNode,
  type NodeDetail,
  type ReviewRequest,
} from "./api";

const names: Record<string, string> = {
  claim: "主张",
  method: "方法",
  finding: "结果",
  condition: "条件",
  concept: "概念",
  experiment: "实验",
  metric: "指标",
};
const reviewNames: Record<string, string> = {
  unreviewed: "未审核",
  needs_review: "待审查",
  accepted: "已接受",
  rejected: "已驳回",
  proposed: "候选",
  superseded: "已替代",
};
const origins: Record<string, string> = {
  author_claim: "作者主张",
  authors_experimental_result: "本文实验结果",
  authors_hypothesis: "作者假设",
  cited_claim: "转述他人",
  background: "背景知识",
  unknown: "归属待确认",
};
const errorText = (e: unknown) => (e instanceof Error ? e.message : String(e));

export function KnowledgeReading({
  versionId,
  connected,
}: {
  versionId: string;
  connected: boolean;
}) {
  const [open, setOpen] = useState(false);
  return (
    <section className="knowledge-area">
      <button
        className="button secondary"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        论文结构与知识 {open ? "收起" : "展开"}
      </button>
      {open && (
        <Reading key={versionId} versionId={versionId} connected={connected} />
      )}
    </section>
  );
}

function Reading({
  versionId,
  connected,
}: {
  versionId: string;
  connected: boolean;
}) {
  const client = useQueryClient();
  const [provider, setProvider] = useState<"mock" | "configured">("mock");
  const [allow, setAllow] = useState(false);
  const [selected, setSelected] = useState("");
  const selection = useRef("");
  const [evidenceId, setEvidenceId] = useState("");
  const [sectionId, setSectionId] = useState("");
  const [kind, setKind] = useState("");
  const structure = useQuery({
    queryKey: ["structure", versionId],
    queryFn: () => api.structure(versionId),
    enabled: connected,
    refetchInterval: 3000,
  });
  const knowledge = useQuery({
    queryKey: ["knowledge", versionId],
    queryFn: () => api.knowledge(versionId),
    enabled: connected,
    refetchInterval: 2000,
  });
  const providers = useQuery({
    queryKey: ["providers"],
    queryFn: api.providers,
    enabled: connected,
  });
  const runs = useQuery({
    queryKey: ["runs", versionId],
    queryFn: () => api.runs(versionId),
    enabled: connected,
    refetchInterval: 2000,
  });
  const detail = useQuery({
    queryKey: ["node", selected],
    queryFn: () => api.node(selected),
    enabled: connected && !!selected,
  });
  const preview = useQuery({
    queryKey: ["preview", evidenceId],
    queryFn: () => api.preview(evidenceId),
    enabled: connected && !!evidenceId,
    retry: false,
  });
  const extract = useMutation({
    mutationFn: () => api.extract(versionId, provider, allow),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["jobs"] });
    },
  });
  const evidence = structure.data?.evidence.find((e) => e.id === evidenceId);
  const cards =
    knowledge.data?.items.filter((n) => !kind || n.kind === kind) ?? [];
  async function choose(node: KnowledgeNode) {
    selection.current = node.id;
    setSelected(node.id);
    setEvidenceId("");
    setSectionId("");
    if (!connected) return;
    try {
      const result = await client.fetchQuery({
        queryKey: ["node", node.id],
        queryFn: () => api.node(node.id),
      });
      if (selection.current !== node.id) return;
      setEvidenceId(result.evidence[0]?.id ?? "");
      setSectionId(result.evidence[0]?.section_id ?? "");
    } catch {
      // The detail query renders the error; no stale evidence is shown.
    }
  }
  return (
    <div>
      <h3>Paper & Reading</h3>
      <p className="quiet-note">
        来源已验证表示能回查原文；人工接受也不代表科学命题已被证明。
      </p>
      <div className="import-controls">
        <label>
          抽取方式{" "}
          <select
            value={provider}
            disabled={!connected}
            onChange={(e) => {
              setProvider(e.target.value as typeof provider);
              setAllow(false);
            }}
          >
            <option value="mock">离线 Mock · 原文摘录验证</option>
            <option value="configured" disabled={!providers.data?.configured}>
              已配置模型 {providers.data?.model ?? "（未配置）"}
            </option>
          </select>
        </label>
        <button
          className="button primary"
          disabled={
            !connected ||
            extract.isPending ||
            (provider === "configured" && !allow)
          }
          onClick={() => extract.mutate()}
        >
          开始结构化抽取
        </button>
      </div>
      {provider === "mock" ? (
        <p className="quality-note">
          Mock 只摘录原文并验证保存/审核流程，不作为真实 LLM 科学抽取结果。
        </p>
      ) : (
        <label className="quality-note">
          <input
            type="checkbox"
            checked={allow}
            onChange={(e) => setAllow(e.target.checked)}
          />{" "}
          同意向已配置模型发送当前论文解析片段及证据
          ID。私人笔记不参与此次抽取。
        </label>
      )}
      {extract.isSuccess && (
        <p role="status">
          抽取任务已排队，可在上方任务记录查看阶段、取消或重试。
        </p>
      )}
      {[structure.error, knowledge.error, detail.error, extract.error]
        .filter(Boolean)
        .map((e, i) => (
          <p role="alert" className="error-text" key={i}>
            {errorText(e)}
          </p>
        ))}
      <div className="reading-grid">
        <nav className="reading-sections" aria-label="论文章节">
          <h4>章节与证据</h4>
          {structure.data?.sections.map((section) => (
            <button
              className={
                sectionId === section.id ? "paper-item selected" : "paper-item"
              }
              key={section.id}
              onClick={() => {
                selection.current = "";
                setSectionId(section.id);
                setEvidenceId(
                  structure.data?.evidence.find(
                    (e) => e.section_id === section.id,
                  )?.id ?? "",
                );
              }}
            >
              {section.title}
              <small>
                {section.role === "other" ? "结构待确认" : section.role}
              </small>
            </button>
          ))}
          {!structure.data?.sections.length && (
            <p>没有文本结构，扫描件需要另行处理。</p>
          )}
        </nav>
        <div className="evidence-reading" aria-label="证据原文">
          <h4>原文回查</h4>
          {evidence ? (
            <>
              <p>
                PDF 第 {evidence.page_index + 1} 页 · 字符 [
                {evidence.start_offset}, {evidence.end_offset})
              </p>
              <pre className="evidence-quote">
                <mark>{evidence.quote}</mark>
              </pre>
              {preview.isFetching && <p>正在加载 PDF 原页面…</p>}
              {preview.error && (
                <p className="quality-note">{errorText(preview.error)}</p>
              )}
              {preview.data && (
                <>
                  <p className="muted">黄色为解析文本块范围，非逐字高亮。</p>
                  <img
                    className="pdf-preview"
                    src={preview.data.data_url}
                    alt={`PDF 第 ${preview.data.page_index + 1} 页原文块高亮`}
                  />
                </>
              )}
            </>
          ) : (
            <p className="muted">
              选择章节或卡片中的证据，核对原页面与解析文本。
            </p>
          )}
          {structure.data?.evidence
            .filter((e) => e.section_id === sectionId)
            .map((e, i) => (
              <button
                className="text-button"
                key={e.id}
                onClick={() => setEvidenceId(e.id)}
              >
                原文片段 {i + 1}
              </button>
            ))}
        </div>
        <div className="knowledge-cards">
          <h4>知识卡片 · {knowledge.data?.items.length ?? 0}</h4>
          <label>
            类型{" "}
            <select value={kind} onChange={(e) => setKind(e.target.value)}>
              <option value="">全部</option>
              {Object.entries(names).map(([v, n]) => (
                <option value={v} key={v}>
                  {n}
                </option>
              ))}
            </select>
          </label>
          {cards.map((node) => (
            <button
              className={
                selected === node.id
                  ? "knowledge-card selected"
                  : "knowledge-card"
              }
              onClick={() => void choose(node)}
              key={node.id}
            >
              <span>
                {names[node.kind]} · {reviewNames[node.review_status]}
              </span>
              <strong>{node.text}</strong>
              <small>
                {node.source_status === "source_verified"
                  ? "来源已验证"
                  : "来源未验证"}{" "}
                · {origins[node.origin] ?? node.origin}
              </small>
              {node.kind === "condition" && (
                <small>
                  {node.known_state} · {node.value ?? "未知/不适用"} {node.unit}
                </small>
              )}
            </button>
          ))}
          {!cards.length && (
            <p className="muted">
              尚无此类知识。抽取完成后，候选内容会显示在这里。
            </p>
          )}
        </div>
      </div>
      {detail.data && (
        <ReviewCard
          key={`${detail.data.node.id}:${detail.data.node.revision}`}
          detail={detail.data}
          connected={connected}
          onEvidence={(id) => {
            setEvidenceId(id);
            setSectionId(
              structure.data?.evidence.find((e) => e.id === id)?.section_id ??
                "",
            );
          }}
        />
      )}
      <details>
        <summary>模型调用与原始结果 · {runs.data?.length ?? 0} 次</summary>
        {runs.data?.map((run) => (
          <article className="text-chunk" key={run.id}>
            <strong>
              {run.prompt_name} · {run.provider}/{run.model} · {run.status}
            </strong>
            <p className="mono small">
              Prompt {run.prompt_hash}
              <br />
              输入 {run.input_hash}
            </p>
            {run.error && <p className="error-text">{run.error}</p>}
            <details>
              <summary>原始输出</summary>
              <pre>{run.raw_output ?? "未返回输出"}</pre>
            </details>
          </article>
        ))}
      </details>
      <ZoteroAnnotations
        versionId={versionId}
        connected={connected}
        onEvidence={setEvidenceId}
      />
    </div>
  );
}

function ReviewCard({
  detail,
  connected,
  onEvidence,
}: {
  detail: NodeDetail;
  connected: boolean;
  onEvidence: (id: string) => void;
}) {
  const client = useQueryClient();
  const node = detail.node;
  const field =
    node.kind === "claim" || node.kind === "finding"
      ? "statement"
      : node.kind === "concept"
        ? "canonical_name"
        : node.kind === "experiment"
          ? "label"
          : node.kind === "condition"
            ? "value"
            : "name";
  const [text, setText] = useState(String(node.payload[field] ?? ""));
  const [origin, setOrigin] = useState(node.origin);
  const [reason, setReason] = useState("");
  const [value, setValue] = useState(node.value ?? "");
  const [unit, setUnit] = useState(node.unit ?? "");
  const [known, setKnown] = useState(node.known_state ?? "unknown");
  const review = useMutation({
    mutationFn: (action: ReviewRequest["action"]) => {
      const payload = { ...node.payload, [field]: text };
      if (node.kind === "claim") payload.origin = origin;
      if (node.kind === "finding") {
        payload.value = value || null;
        payload.unit = unit || null;
      }
      if (node.kind === "condition") {
        payload.known_state = known;
        payload.value =
          known === "unknown" || known === "not_applicable" ? null : text;
        payload.unit = unit || null;
      }
      return api.review({
        node_id: node.id,
        expected_revision: node.revision,
        expected_graph_revision: detail.graph_revision,
        action,
        reason,
        payload: action === "revise" ? payload : null,
      });
    },
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["node", node.id] });
      void client.invalidateQueries({
        queryKey: ["knowledge", node.document_version_id],
      });
    },
  });
  return (
    <section className="review-panel" aria-label="知识审核">
      <h4>
        {names[node.kind]}审核 · 版本 {node.revision}
      </h4>
      <div>
        {detail.evidence.map((e, i) => (
          <button
            className="button secondary"
            key={e.id}
            onClick={() => onEvidence(e.id)}
          >
            查看证据 {i + 1} · 第 {e.page_index + 1} 页
          </button>
        ))}
      </div>
      {node.issues.length > 0 && (
        <p className="quality-note">待核对：{node.issues.join("、")}</p>
      )}
      <label>
        修订内容
        <textarea
          aria-label="修订内容"
          value={text}
          onChange={(e) => setText(e.target.value)}
          disabled={!connected}
        />
      </label>
      {node.kind === "claim" && (
        <label>
          主张归属{" "}
          <select value={origin} onChange={(e) => setOrigin(e.target.value)}>
            {Object.entries(origins).map(([v, n]) => (
              <option key={v} value={v}>
                {n}
              </option>
            ))}
          </select>
        </label>
      )}
      {node.kind === "condition" && (
        <label>
          条件状态{" "}
          <select
            value={known}
            onChange={(e) => setKnown(e.target.value as typeof known)}
          >
            {["known", "unknown", "not_applicable", "conflicting"].map((v) => (
              <option key={v}>{v}</option>
            ))}
          </select>
        </label>
      )}
      {node.kind === "finding" && (
        <label>
          数值{" "}
          <input value={value} onChange={(e) => setValue(e.target.value)} />
        </label>
      )}
      {["finding", "condition"].includes(node.kind) && (
        <label>
          单位 <input value={unit} onChange={(e) => setUnit(e.target.value)} />
        </label>
      )}
      <label>
        审核或修改理由{" "}
        <input
          aria-label="审核理由"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          maxLength={2000}
        />
      </label>
      <div className="import-controls">
        {(["revise", "accept", "reject"] as const).map((action) => (
          <button
            className="button secondary"
            disabled={
              !connected ||
              review.isPending ||
              !reason.trim() ||
              (action === "revise" && node.kind === "metric")
            }
            key={action}
            onClick={() => review.mutate(action)}
          >
            {action === "revise"
              ? "保存修订待审"
              : action === "accept"
                ? "接受当前记录"
                : "驳回当前记录"}
          </button>
        ))}
      </div>
      <p className="muted">
        接受/驳回针对当前已保存版本；改动内容请先保存修订。每次操作保留原始模型结果和前后版本。
      </p>
      {review.error && (
        <p role="alert" className="error-text">
          {errorText(review.error)}
        </p>
      )}
      <details>
        <summary>修改与审核历史 · {detail.reviews.length}</summary>
        {detail.reviews.map((r) => (
          <article className="text-chunk" key={r.id}>
            <strong>
              {r.action} · {r.actor}
            </strong>
            <p>
              {r.reason} · {new Date(r.created_at).toLocaleString("zh-CN")}
            </p>
            <pre>
              {String(r.before.text ?? "")} → {String(r.after.text ?? "")}
            </pre>
          </article>
        ))}
      </details>
    </section>
  );
}

function ZoteroAnnotations({
  versionId,
  connected,
  onEvidence,
}: {
  versionId: string;
  connected: boolean;
  onEvidence: (id: string) => void;
}) {
  const [item, setItem] = useState("");
  const [attachment, setAttachment] = useState("");
  const client = useQueryClient();
  const notes = useQuery({
    queryKey: ["annotations", versionId],
    queryFn: () => api.annotations(versionId),
    enabled: connected,
  });
  const importing = useMutation({
    mutationFn: () => api.importAnnotations(versionId, item, attachment),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["annotations", versionId] });
    },
  });
  return (
    <details>
      <summary>Zotero 批注 · {notes.data?.length ?? 0}</summary>
      <p>
        先通过 PDF 选择器导入 Zotero 的对应附件。仅从本地 API
        读取条目与批注，不修改 Zotero 数据。
      </p>
      <label>
        源条目 Key{" "}
        <input
          value={item}
          onChange={(e) => setItem(e.target.value.toUpperCase())}
          maxLength={8}
        />
      </label>
      <label>
        附件 Key{" "}
        <input
          value={attachment}
          onChange={(e) => setAttachment(e.target.value.toUpperCase())}
          maxLength={8}
        />
      </label>
      <button
        className="button secondary"
        disabled={
          !connected ||
          item.length !== 8 ||
          attachment.length !== 8 ||
          importing.isPending
        }
        onClick={() => importing.mutate()}
      >
        读取并关联批注
      </button>
      {importing.error && <p role="alert">{errorText(importing.error)}</p>}
      {importing.data && (
        <p>
          新增 {importing.data.added} 条，未解析锚点 {importing.data.unresolved}{" "}
          条。
        </p>
      )}
      {notes.data?.map((n) => (
        <article className="text-chunk" key={n.id}>
          <blockquote>{n.text}</blockquote>
          <p>用户评论：{n.comment}</p>
          <small>
            {n.source_item_key}/{n.annotation_key} ·{" "}
            {n.anchor_status === "unresolved" ? "锚点未解析" : "匹配原文块"}
          </small>
          {n.evidence_id && (
            <button
              className="text-button"
              onClick={() => onEvidence(n.evidence_id!)}
            >
              查看关联原文
            </button>
          )}
        </article>
      ))}
    </details>
  );
}

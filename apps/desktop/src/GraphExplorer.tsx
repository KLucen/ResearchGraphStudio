import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { components } from "../../../packages/contracts/generated";
import { api, request, type Evidence, type Job } from "./api";
import { JobHistory } from "./JobHistory";

type Graph = components["schemas"]["GraphView"];
type Context = components["schemas"]["ContextView"];
type History = components["schemas"]["ReasoningHistory"];
type Proposal = components["schemas"]["ProposalView"];
type Detail = components["schemas"]["ProposalDetail"];
const statusNames: Record<string, string> = {
  proposed: "模型候选",
  unreviewed: "来源候选",
  needs_review: "有限证据",
  accepted: "历史已接受",
  rejected: "历史已驳回",
  superseded: "历史已替代",
};
const kindNames: Record<string, string> = {
  claim: "主张",
  concept: "概念",
  method: "方法",
};
const errorText = (e: unknown) => (e instanceof Error ? e.message : String(e));
function displayText(node: Graph["nodes"][number]): string {
  const payload = (node.payload ?? {}) as Record<string, unknown>;
  return String(
    payload.statement_zh ||
      payload.canonical_name_zh ||
      payload.name_zh ||
      node.text,
  );
}

export function GraphExplorer({
  projectId,
  connected,
  initialSourceId = "",
}: {
  projectId: string;
  connected: boolean;
  initialSourceId?: string;
}) {
  const client = useQueryClient();
  const [kind, setKind] = useState("claim");
  const [cursors, setCursors] = useState([""]);
  const [focusId, setFocusId] = useState("");
  const [sourceId, setSourceId] = useState(initialSourceId);
  const [targetId, setTargetId] = useState("");
  const [query, setQuery] = useState("");
  const [topK, setTopK] = useState(10);
  const provider = "project";
  const [allow, setAllow] = useState(false);
  const [selectedProposal, setSelectedProposal] = useState<{
    id: string;
    kind: "relation" | "alignment";
  } | null>(null);
  const graph = useQuery({
    queryKey: ["graph", projectId, kind, cursors.at(-1), focusId],
    queryFn: () =>
      request<Graph>(
        "GET",
        `/api/v1/graph/subgraph?project_id=${projectId}&kind=${kind}&status=all&limit=24&cursor=${cursors.at(-1)}&focus_id=${focusId}&include_test_data=false`,
      ),
    enabled: connected,
    refetchInterval: 5000,
  });
  const history = useQuery({
    queryKey: ["reasoning", projectId],
    queryFn: () =>
      request<History>("GET", `/api/v1/projects/${projectId}/reasoning`),
    enabled: connected,
    refetchInterval: 3000,
  });
  const source = useQuery({
    queryKey: ["context", sourceId],
    queryFn: () =>
      request<Context>("GET", `/api/v1/knowledge/nodes/${sourceId}/context`),
    enabled: connected && !!sourceId,
    refetchInterval: 5000,
  });
  const target = useQuery({
    queryKey: ["context", targetId],
    queryFn: () =>
      request<Context>("GET", `/api/v1/knowledge/nodes/${targetId}/context`),
    enabled: connected && !!targetId,
    refetchInterval: 5000,
  });
  const recall = useMutation({
    mutationFn: () =>
      request<components["schemas"]["CandidateList"]>(
        "POST",
        "/api/v1/knowledge/candidates",
        { source_id: sourceId, query, top_k: topK, include_test_data: false },
      ),
  });
  const selectedKind =
    source.data?.nodes.find((n) => n.id === sourceId)?.kind ?? kind;
  const infer = useMutation({
    mutationFn: () =>
      request<Job>(
        "POST",
        `/api/v1/knowledge/${selectedKind === "claim" ? "relations" : "alignments"}/infer`,
        {
          source_id: sourceId,
          target_id: targetId,
          provider,
          allow_network: allow,
        },
        crypto.randomUUID(),
      ),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["jobs", projectId] });
    },
  });
  function chooseSource(id: string) {
    setSourceId(id);
    setTargetId("");
    setSelectedProposal(null);
    recall.reset();
    infer.reset();
  }
  function chooseProposal(p: Proposal, mode: "relation" | "alignment") {
    setSelectedProposal({ id: p.id, kind: mode });
    setSourceId(p.source_id);
    setTargetId(p.target_id);
    if (mode === "relation") {
      setKind("claim");
      setFocusId(p.source_id);
      setCursors([""]);
    }
  }
  const allProposals = [
    ...(history.data?.relations ?? []).map((p) => ({
      p,
      mode: "relation" as const,
    })),
    ...(history.data?.alignments ?? []).map((p) => ({
      p,
      mode: "alignment" as const,
    })),
  ];
  const dimensions = [
    ...new Set([
      ...Object.keys(source.data?.dimensions ?? {}),
      ...Object.keys(target.data?.dimensions ?? {}),
    ]),
  ];
  return (
    <section className="graph-workbench" aria-label="知识图谱与主张比较">
      <div className="heading-row">
        <div>
          <h2>主张比较与实体对齐</h2>
        </div>
        <span>图谱版本 {graph.data?.graph_revision ?? "—"}</span>
      </div>
      <p className="quiet-note">
        选择节点检索其他论文的候选，再并排核对条件和原文。虚线表示模型候选关系，关系类型和证据来源始终单独显示。
      </p>
      <div className="import-controls">
        <label>
          节点类型{" "}
          <select
            value={kind}
            onChange={(e) => {
              setKind(e.target.value);
              setCursors([""]);
              setFocusId("");
              chooseSource("");
            }}
          >
            <option value="claim">主张</option>
            <option value="concept">概念</option>
            <option value="method">方法</option>
          </select>
        </label>
        <button
          className="text-button"
          disabled={!sourceId}
          onClick={() => {
            setFocusId(sourceId);
            setCursors([""]);
          }}
        >
          聚焦所选节点与关系
        </button>
        <button
          className="text-button"
          onClick={() => {
            setFocusId("");
            setCursors([""]);
          }}
        >
          浏览项目节点
        </button>
        <button
          className="text-button"
          disabled={cursors.length === 1}
          onClick={() => setCursors(cursors.slice(0, -1))}
        >
          上一页节点
        </button>
        <button
          className="text-button"
          disabled={!graph.data?.next_cursor}
          onClick={() => setCursors([...cursors, graph.data!.next_cursor!])}
        >
          下一页节点
        </button>
      </div>
      <details open>
        <summary>选择比较来源 · {graph.data?.nodes.length ?? 0}</summary>
        <div className="graph-node-list">
          {graph.data?.nodes.map((n) => (
            <button
              className="knowledge-card"
              key={n.id}
              onClick={() => chooseSource(n.id)}
            >
              <small>
                {kindNames[n.kind]} · {statusNames[n.review_status]}
              </small>
              {displayText(n)}
            </button>
          ))}
        </div>
      </details>
      {[
        graph.error,
        history.error,
        source.error,
        target.error,
        recall.error,
        infer.error,
      ]
        .filter(Boolean)
        .map((e, i) => (
          <p role="alert" className="error-text" key={i}>
            {errorText(e)}
          </p>
        ))}
      <div className="comparison-heading">
        <h3>
          {selectedKind === "claim"
            ? "Claim Comparator · 主张比较"
            : "实体对齐候选"}
        </h3>
        <p>
          知识来自论文作者；模型关系是推断。unknown
          表示未记录，不能当作条件相同。
        </p>
      </div>
      {!sourceId && <p>先从图谱或节点列表选择一个{kindNames[kind]}。</p>}
      {sourceId && (
        <>
          <div className="import-controls">
            <label>
              候选关键词{" "}
              <input
                value={query}
                maxLength={300}
                placeholder="留空使用所选节点文本"
                onChange={(e) => setQuery(e.target.value)}
              />
            </label>
            <label>
              召回数量{" "}
              <input
                type="number"
                min={1}
                max={30}
                value={topK}
                onChange={(e) =>
                  setTopK(
                    Math.max(1, Math.min(30, Number(e.target.value) || 1)),
                  )
                }
              />
            </label>
            <button
              className="button secondary"
              disabled={!connected || recall.isPending}
              onClick={() => recall.mutate()}
            >
              检索跨论文候选
            </button>
          </div>
          {recall.data && (
            <div className="candidate-results" aria-label="候选检索结果">
              <small>
                FTS5 / BM25 · {recall.data.items.length}{" "}
                项；词项匹配只表示召回依据。
              </small>
              {recall.data.items.map((n) => (
                <button
                  key={n.id}
                  className={`knowledge-card${targetId === n.id ? " selected" : ""}`}
                  onClick={() => {
                    setTargetId(n.id);
                    setSelectedProposal(null);
                    infer.reset();
                  }}
                >
                  {displayText(n)}
                  <small>
                    {statusNames[n.review_status]} · {n.origin}
                  </small>
                </button>
              ))}
              {!recall.data.items.length && <p>没有匹配候选，可调整关键词。</p>}
            </div>
          )}
          <div className="comparator-columns">
            <KnowledgeSide
              context={source.data}
              label="来源 A"
              connected={connected}
            />
            <KnowledgeSide
              context={target.data}
              label="来源 B"
              connected={connected}
            />
          </div>
          {!!targetId && (
            <>
              <div className="condition-table">
                <table>
                  <caption>当前条件节点</caption>
                  <thead>
                    <tr>
                      <th>维度</th>
                      <th>来源 A</th>
                      <th>来源 B</th>
                    </tr>
                  </thead>
                  <tbody>
                    {dimensions.map((name) => (
                      <tr key={name}>
                        <th>{name}</th>
                        {[source.data, target.data].map((c, index) => {
                          const d = c?.dimensions[name];
                          return (
                            <td key={index}>
                              {String(d?.known_state ?? "unknown")}
                              <br />
                              {String(d?.value ?? "未记录 / 不适用")}{" "}
                              {String(d?.unit ?? "")}
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="import-controls">
                <span>全局 Reasoning 模型</span>
                <button
                  className="button primary"
                  disabled={
                    !connected ||
                    !source.data ||
                    !target.data ||
                    infer.isPending ||
                    !allow
                  }
                  onClick={() => infer.mutate()}
                >
                  {selectedKind === "claim"
                    ? "比较条件并推理关系"
                    : "生成实体对齐候选"}
                </button>
              </div>
              <label className="quality-note">
                <input
                  type="checkbox"
                  checked={allow}
                  onChange={(e) => setAllow(e.target.checked)}
                />{" "}
                同意向全局 Reasoning
                模型发送双方主张、实验条件与原文证据。私人笔记不参与。
              </label>
              {infer.isSuccess && (
                <p role="status">推理任务已排队，完成后显示在下方记录中。</p>
              )}
            </>
          )}
        </>
      )}
      <JobHistory projectId={projectId} connected={connected} />
      <h3>模型推理记录 · 最近 50 次</h3>
      <div className="proposal-list">
        {allProposals.map(({ p, mode }) => (
          <button
            key={p.id}
            className="knowledge-card"
            onClick={() => chooseProposal(p, mode)}
          >
            <small>
              {mode === "relation" ? "关系" : "实体对齐"} ·{" "}
              {statusNames[p.review_status]}
              {p.stale ? " · 来源已变化" : ""}
            </small>
            <strong>{p.relation_type}</strong>
            <span>{p.rationale}</span>
          </button>
        ))}
      </div>
      {history.data?.attempts
        .filter((a) => !allProposals.some(({ p }) => p.attempt_id === a.id))
        .map((a) => (
          <details key={a.id}>
            <summary>
              未形成关系 / NO_DECISION ·{" "}
              {new Date(a.created_at).toLocaleString("zh-CN")}
            </summary>
            <p>{String(a.output.reason ?? "没有足够依据生成候选")}</p>
            <pre>{JSON.stringify(a.comparison, null, 2)}</pre>
          </details>
        ))}
      {selectedProposal && (
        <ProposalReview
          key={selectedProposal.id}
          selection={selectedProposal}
          connected={connected}
        />
      )}
    </section>
  );
}

function KnowledgeSide({
  context,
  label,
  connected,
}: {
  context?: Context;
  label: string;
  connected: boolean;
}) {
  const node = context?.nodes.find((n) => n.id === context.root_id);
  const [evidenceId, setEvidenceId] = useState("");
  const evidence =
    context?.evidence.find((e) => e.id === evidenceId) ??
    context?.evidence.find((e) => e.id === context.root_evidence_ids[0]);
  return (
    <section className="comparator-side" aria-label={label}>
      <h4>{label}</h4>
      {node ? (
        <>
          <small>
            {kindNames[node.kind]} · {statusNames[node.review_status]} ·{" "}
            {node.origin}
          </small>
          <p>{node.text}</p>
          <p>
            来源状态：{node.source_status} · 知识版本 {node.revision}
          </p>
          <div className="evidence-choices">
            {context?.root_evidence_ids.map((id, i) => (
              <button
                key={id}
                className="text-button"
                onClick={() => setEvidenceId(id)}
              >
                证据 {i + 1}
              </button>
            ))}
          </div>
          {evidence && (
            <EvidencePanel
              key={evidence.id}
              evidence={evidence}
              connected={connected}
            />
          )}
        </>
      ) : (
        <p>选择另一篇论文的候选以比较。</p>
      )}
    </section>
  );
}

function EvidencePanel({
  evidence,
  connected,
}: {
  evidence: Evidence;
  connected: boolean;
}) {
  const [open, setOpen] = useState(false);
  const preview = useQuery({
    queryKey: ["preview", evidence.id],
    queryFn: () => api.preview(evidence.id),
    enabled: connected && open,
    retry: false,
  });
  return (
    <div>
      <small>
        PDF 第 {evidence.page_index + 1} 页 · 字符 [{evidence.start_offset},{" "}
        {evidence.end_offset})
      </small>
      <blockquote className="comparison-quote">{evidence.quote}</blockquote>
      <button className="button secondary" onClick={() => setOpen(!open)}>
        {open ? "收起 PDF 原文" : "定位 PDF 原文"}
      </button>
      {open && (
        <>
          {preview.isPending && <p>正在定位…</p>}
          {preview.error && <p role="alert">{errorText(preview.error)}</p>}
          {preview.data && (
            <img
              className="pdf-preview"
              src={preview.data.data_url}
              alt={`PDF 第 ${evidence.page_index + 1} 页的证据块高亮`}
            />
          )}
        </>
      )}
    </div>
  );
}

export function ProposalReview({
  selection,
  connected,
}: {
  selection: { id: string; kind: "relation" | "alignment" };
  connected: boolean;
}) {
  const detail = useQuery({
    queryKey: ["proposal", selection.id],
    queryFn: () =>
      request<Detail>(
        "GET",
        `/api/v1/knowledge/${selection.kind === "relation" ? "relations" : "alignments"}/${selection.id}`,
      ),
    enabled: connected,
    refetchInterval: 5000,
  });
  const data = detail.data;
  return (
    <section className="review-panel" aria-label="关系与实体解释">
      <h3>AI 关系解释</h3>
      {detail.error && <p role="alert">{errorText(detail.error)}</p>}
      {data && (
        <>
          <strong>{data.proposal.relation_type} · AI 推断</strong>
          <p>
            {String(
              data.attempt.output?.reason_zh ||
                data.attempt.output?.rationale_zh ||
                data.proposal.rationale,
            )}
          </p>
          <details>
            <summary>英文解释</summary>
            <p>{data.proposal.rationale}</p>
          </details>
          {data.proposal.stale && (
            <p role="alert">来源已变化，请重新推理。原判断和历史仍保留。</p>
          )}
          {selection.kind === "alignment" && (
            <p>对齐建议保留为模型推断，不自动合并或改写原实体。</p>
          )}
          {data.attempt.comparison && (
            <details open>
              <summary>条件可比性报告</summary>
              <p>
                {String(data.attempt.comparison.overall)} ·{" "}
                {String(
                  data.attempt.comparison.rationale_zh ||
                    data.attempt.comparison.rationale,
                )}
              </p>
              <pre>
                {JSON.stringify(data.attempt.comparison.dimensions, null, 2)}
              </pre>
            </details>
          )}
          <h4>模型来源与原始结果</h4>
          {data.runs.map((r) => (
            <details key={r.id}>
              <summary>
                {r.prompt_name} · {r.provider} / {r.model} · {r.status}
              </summary>
              <p>
                Prompt {r.prompt_hash} · 输入 {r.input_hash}
              </p>
              <pre>{JSON.stringify(r.parameters, null, 2)}</pre>
              <pre>{r.raw_output}</pre>
            </details>
          ))}
          <h4>历史记录 · {data.reviews.length}</h4>
          {data.reviews.map((r) => (
            <details key={r.id}>
              <summary>
                {r.action} · {r.reason}
              </summary>
              <pre>
                {JSON.stringify({ before: r.before, after: r.after }, null, 2)}
              </pre>
            </details>
          ))}
        </>
      )}
    </section>
  );
}

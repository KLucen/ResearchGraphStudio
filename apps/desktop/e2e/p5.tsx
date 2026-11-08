import { StrictMode, useState } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { mockIPC } from "@tauri-apps/api/mocks";
import { P5Workspace } from "../src/P5Workspace";
import type {
  LintRun,
  WikiPageView,
  WorkflowView,
  WikiPublication,
  ExternalDocument,
} from "../src/p5Api";
import "../src/style.css";

type IPCRequest = {
  method: string;
  path: string;
  body: Record<string, unknown> | null;
  idempotencyKey: string | null;
};
declare global {
  interface Window {
    p5Harness: {
      requests: IPCRequest[];
      unexpected: string[];
      authorizations: number;
      finishLintPreparation?: () => void;
      finishLintRebuild?: () => void;
    };
  }
}
// Only distributable synthetic fixtures. Every unknown IPC fails; this harness
// cannot access an engine, a model, credentials, private files or a native vault.
const projectId = "synthetic-p5";
const storageKey = "researchgraph.synthetic-p5.fixture";
const now = "2026-11-05T13:00:00+08:00";
const state: {
  draft: boolean;
  saved: boolean;
  published: boolean;
  operations: WikiPublication[];
  workflow: string;
} = JSON.parse(localStorage.getItem(storageKey) ?? "null") ?? {
  draft: false,
  saved: false,
  published: false,
  operations: [],
  workflow: "",
};
const conflict = new URLSearchParams(location.search).has("conflict");
const lintPhases = new URLSearchParams(location.search).has("lintPhases");
if (conflict) {
  state.draft = true;
  state.saved = true;
  state.published = true;
  state.operations = [
    { operation_id: "interrupted-publication", state: "staged" },
  ];
}
const persist = () => localStorage.setItem(storageKey, JSON.stringify(state));
window.p5Harness = { requests: [], unexpected: [], authorizations: 0 };
let annotationModelAllowed = false;
let annotationLocalAllowed = true;
let registeredExternal: ExternalDocument | null = null;
const root = {
  root_id: "root-1",
  path: "合成独立输出目录",
  active: true,
  revision: 1,
};
const run: LintRun = {
  id: "lint-1",
  project_id: projectId,
  status: "completed",
  scope: {
    paper_ids: ["paper-1", "paper-2"],
    document_ids: [],
    include_personal: false,
  },
  rule_version: "synthetic-rules-1",
  event_sequence: 0,
  input_hash: "frozen-input",
  total: 25,
  processed: 25,
  progress: 1,
  counts: { error: 1, warning: 0, info: 0 },
  diff: { new: 1, persistent: 0, resolved: 0 },
  previous_run_id: null,
  errors: [],
  created_at: now,
  updated_at: now,
  finished_at: now,
};
let currentLintRun = run;
const wiki = (): WikiPageView => ({
  page_id: "page-1",
  title: "合成方法的条件与限制",
  version_id: "version-1",
  head_version_id: "version-1",
  saved_version_id: state.saved ? "version-1" : null,
  revision: 1,
  state: state.saved ? "saved" : "draft",
  content_state: "valid",
  content_hash: "a".repeat(64),
  markdown: "# 合成方法的条件与限制\n\n仅在指定条件下有效。",
  diff: "+仅在指定条件下有效。",
  sections: [
    {
      section_id: "section-1",
      heading: "方法与条件",
      text: "合成方法仅在指定条件下有效，不外推其他范围。",
      attribution: "model_synthesis",
      dependencies: [
        {
          type: "evidence",
          id: "evidence-1",
          quote: "Synthetic methods under explicit conditions.",
        },
      ],
      caveats: ["仍有未覆盖条件"],
      conditions: [
        { dimension: "温度", state: "known", value: "20", unit: "C" },
      ],
      stale: false,
    },
  ],
  versions: [
    {
      version_id: "version-1",
      revision: 1,
      state: state.saved ? "saved" : "draft",
      content_hash: "a".repeat(64),
    },
  ],
  file: state.published
    ? {
        root_id: root.root_id,
        state: conflict ? "modified" : "in_sync",
        sha256: "b".repeat(64),
        current_hash: conflict ? "c".repeat(64) : "b".repeat(64),
      }
    : { state: "not_exported" },
});
const workflow = (): WorkflowView => ({
  id: "workflow-1",
  kind: "wiki_synthesis",
  status: state.workflow || "prepared",
  input_hash: "frozen-workflow",
  job_id: state.workflow ? "job-1" : null,
  question: "论文阅读：合成方法条件",
  can_continue: false,
  error_code: null,
  error: null,
  created_at: now,
  model_runs: state.workflow
    ? [
        {
          id: "model-1",
          status: "succeeded",
          usage: { total_tokens: 20 },
          duration_seconds: 1,
          error_code: null,
          error: null,
          cost_known: false,
        },
      ]
    : [],
  result: state.workflow
    ? {
        draft: { title: wiki().title, passages: wiki().sections },
        coverage_gaps: ["合成范围外不作推断"],
      }
    : null,
});

mockIPC(async (command, args = {}) => {
  if (command === "wiki_authorize_output") {
    window.p5Harness.authorizations++;
    return root;
  }
  const reject = (reason: string): never => {
    window.p5Harness.unexpected.push(reason);
    throw reason;
  };
  if (command !== "engine_request")
    return reject(`Unexpected command ${command}`);
  const request = args as IPCRequest;
  window.p5Harness.requests.push(request);
  const route = new URL(request.path, "http://synthetic.invalid").pathname;
  const base = `/api/v1/projects/${projectId}`;
  if (route === `${base}/lint/documents`)
    return {
      items: [
        {
          id: "page-1",
          title: "合成阅读草稿",
          kind: "wiki",
          status: "draft",
          current_version_id: null,
          latest_version_id: "version-1",
        },
      ],
      total: 1,
      page: 1,
      page_size: 10,
    };
  if (route === `${base}/p5/personal-sources`)
    return {
      items: [
        {
          type: "annotation",
          id: "annotation-1",
          label: annotationLocalAllowed
            ? "合成个人评论"
            : "已撤销本地读取的批注",
          ...(annotationLocalAllowed
            ? {
                text: "我的评论，仅供阅读参考。",
                highlight: "已有原文高亮。",
                sha256: "a".repeat(64),
              }
            : { redacted: true }),
          allow_local: annotationLocalAllowed,
          allow_model: annotationModelAllowed,
          authorization_revision: annotationModelAllowed ? 1 : 0,
        },
        ...(registeredExternal
          ? [
              {
                type: "external",
                id: registeredExternal.version_id,
                label: registeredExternal.title,
                text: registeredExternal.text,
                sha256: registeredExternal.sha256,
                allow_model: true,
                authorization_revision: 1,
                root_id: "read-root",
              },
            ]
          : []),
      ],
      total: registeredExternal ? 2 : 1,
      page: 1,
      page_size: 10,
    };
  if (route === `${base}/p5/annotations/annotation-1/grant`) {
    annotationModelAllowed = request.body?.allow_model === true;
    if (typeof request.body?.allow_local === "boolean")
      annotationLocalAllowed = request.body.allow_local;
    return {
      annotation_id: "annotation-1",
      allow_model: annotationModelAllowed,
      allow_local: annotationLocalAllowed,
      revision: 1,
    };
  }
  if (route === `${base}/note-roots`)
    return [
      {
        id: "read-root",
        path: "合成只读材料目录",
        active: true,
        query_permissions: { allow_local: true, allow_model: true },
      },
    ];
  if (route === "/api/v1/integrations/obsidian/read-root/notes")
    return [
      {
        id: "note-1",
        relative_path: "synthetic.md",
        sha256: "d".repeat(64),
        text: "合成外部私人材料。",
        authorship: "user",
      },
    ];
  if (route === `${base}/external-documents/preview`)
    return {
      root_id: "read-root",
      relative_path: "synthetic.md",
      sha256: "d".repeat(64),
      text: "合成外部私人材料。",
      source_verified: false,
      file_state: "in_sync",
    };
  if (route === `${base}/external-documents` && request.method === "POST") {
    registeredExternal = {
      document_id: "external-1",
      version_id: "external-v1",
      current_version_id: "external-v1",
      title: String(request.body?.title),
      revision: 1,
      attribution: "user_view",
      content_state: "unverified",
      source_verified: false,
      root_id: "read-root",
      relative_path: "synthetic.md",
      sha256: "d".repeat(64),
      text: "合成外部私人材料。",
      file_state: "in_sync",
      versions: [
        {
          version_id: "external-v1",
          revision: 1,
          sha256: "d".repeat(64),
          title: String(request.body?.title),
          attribution: "user_view",
        },
      ],
    };
    return registeredExternal;
  }
  if (route === `${base}/external-documents`)
    return {
      items: registeredExternal ? [registeredExternal] : [],
      total: registeredExternal ? 1 : 0,
    };
  if (route === `${base}/external-documents/external-1`)
    return registeredExternal;
  if (route === `${base}/papers`)
    return {
      items: [
        { id: "paper-1", title: "合成论文一" },
        { id: "paper-2", title: "合成论文二" },
      ],
      next_cursor: null,
    };
  if (route === `${base}/lint/runs` && request.method === "GET")
    return { items: [run], total: 1, page: 1, page_size: 10 };
  if (route === `${base}/lint/runs` && request.method === "POST") {
    if (lintPhases)
      await new Promise<void>((resolve) => {
        window.p5Harness.finishLintPreparation = resolve;
      });
    currentLintRun = {
      ...run,
      status: "queued",
      processed: 0,
      ...(lintPhases ? { phase: "scanning" as const } : {}),
    };
    return currentLintRun;
  }
  if (route === `${base}/lint/runs/lint-1/advance`) {
    if (lintPhases && currentLintRun.phase === "scanning") {
      currentLintRun = {
        ...run,
        status: "running",
        phase: "rebuilding_dependencies",
      };
      return currentLintRun;
    }
    if (lintPhases) {
      await new Promise<void>((resolve) => {
        window.p5Harness.finishLintRebuild = resolve;
      });
      currentLintRun = {
        ...run,
        phase: "finished",
        timings: {
          prepare_seconds: 0.025,
          check_seconds: 0.1,
          dependency_rebuild_seconds: 0.2,
          elapsed_seconds: 0.325,
          advance_calls: 2,
        },
      };
      return currentLintRun;
    }
    return run;
  }
  if (route === `${base}/lint/runs/lint-1`)
    return lintPhases ? currentLintRun : run;
  if (route === `${base}/lint/runs/lint-1/issues`)
    return {
      items: [
        {
          id: "issue-1",
          fingerprint: "issue-fingerprint",
          code: "SOURCE_CHANGED",
          rule_version: run.rule_version,
          severity: "error",
          category: "dependency",
          object_type: "node",
          object_id: "node-1",
          paper_id: "paper-1",
          location: { node_id: "node-1", page_id: "page-1", page_index: 2 },
          message: "合成来源已变化，仅定位受影响内容。",
          suggestion: "重新核验支撑，不改写原文。",
          repair_plan: {
            status: "actionable",
            summary: "先回查来源与条件，再通过受控流程处理受影响内容。",
            steps: [
              {
                id: "review-source",
                title: "核对原文与来源状态",
                description: "在本机回查原文证据与已登记来源。",
                action: "review_source",
                automated: false,
                requires_model: false,
              },
              {
                id: "controlled-rebuild",
                title: "有明确证据时创建新版本",
                description:
                  "通过后续受控流程重建受影响内容，当前方案不直接修改知识。",
                action: "rebuild_affected",
                automated: false,
                requires_model: null,
              },
            ],
            safeguards: [
              "没有明确条件证据时保留 unknown，不推断 conflicting，也不补造条件。",
              "保留原文、历史证据与未受影响内容。",
            ],
          },
          lifecycle: "new",
          deterministic: true,
        },
      ],
      total: 1,
      page: 1,
      page_size: 10,
    };
  if (route === `${base}/lint/dependencies`)
    return {
      items: [
        {
          id: "edge-1",
          dependent_type: "document",
          dependent_id: "page-1",
          source_type: "node",
          source_id: "node-1",
          role: "source",
          category: "dependency",
          state: "stale",
        },
      ],
      total: 1,
      page: 1,
      page_size: 10,
    };
  if (route === `${base}/lint/dependencies/rebuild`)
    return { edge_count: 7, change_count: 1 };
  if (route === `${base}/wiki/pages`)
    return {
      items: state.draft
        ? [
            {
              page_id: "page-1",
              title: wiki().title,
              head_version_id: "version-1",
              saved_version_id: state.saved ? "version-1" : null,
              published_version_id: state.published ? "version-1" : null,
              file_state: wiki().file?.state,
              content_hash: wiki().content_hash,
            },
          ]
        : [],
      total: state.draft ? 1 : 0,
      offset: 0,
      limit: 10,
    };
  if (route === `${base}/wiki/pages/page-1`) return wiki();
  if (route === `${base}/wiki/pages/page-1/save`) {
    state.saved = true;
    persist();
    return wiki();
  }
  if (route === `${base}/wiki/roots`) return { items: [root] };
  if (route === `${base}/wiki/publications`)
    return {
      items: state.operations,
      total: state.operations.length,
      offset: 0,
      limit: 10,
    };
  if (route === `${base}/wiki/pages/page-1/publish`) {
    if (conflict)
      return reject("External modifications must block publication");
    state.published = true;
    state.operations.push({
      operation_id: "publication-1",
      state: "succeeded",
    });
    persist();
    return state.operations.at(-1);
  }
  if (route === `${base}/wiki/pages/page-1/inspect-file`)
    return {
      observation_id: "observation-1",
      attribution: "user_view",
      source_verified: false,
      text: "外部私人修改，未验证来源。",
      diff: "+外部私人修改",
    };
  if (route === `${base}/wiki/publications/interrupted-publication/recover`) {
    const op = {
      operation_id: "interrupted-publication",
      state: "conflict",
      error: "合成外部文件已修改，保留原文件。",
    };
    state.operations = [op];
    persist();
    return op;
  }
  if (route === `${base}/workflows`)
    return { items: state.workflow ? [workflow()] : [] };
  if (route === `${base}/workflows/prepare`) return workflow();
  if (route === `${base}/workflows/workflow-1`) return workflow();
  if (route === `${base}/workflows/workflow-1/generate`) {
    state.workflow = "succeeded";
    persist();
    return { id: "job-1", status: "queued" };
  }
  if (route === `${base}/workflows/workflow-1/materialize`) {
    state.draft = true;
    persist();
    return wiki();
  }
  return reject(`Unexpected ${request.method} ${route}`);
});
function Harness() {
  const [mode, setMode] = useState<"lint" | "wiki">(conflict ? "wiki" : "lint");
  const [focus, setFocus] = useState("");
  return (
    <main style={{ margin: "0 auto", padding: 24, maxWidth: 1160 }}>
      <p>自动化回归 · 合成资料 · 无模型或私人文件访问</p>
      <nav>
        <button onClick={() => setMode("lint")}>Lint 测试页</button>
        <button onClick={() => setMode("wiki")}>Wiki 测试页</button>
      </nav>
      {focus && <p role="status">图谱定位：{focus}</p>}
      <P5Workspace
        key={mode}
        projectId={projectId}
        connected
        mode={mode}
        initialPageId={conflict ? "page-1" : ""}
        onGraphNode={setFocus}
        onWikiPage={() => setMode("wiki")}
      />
    </main>
  );
}
const client = new QueryClient({
  defaultOptions: {
    queries: { retry: false, refetchOnWindowFocus: false },
    mutations: { retry: false },
  },
});
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={client}>
      <Harness />
    </QueryClientProvider>
  </StrictMode>,
);

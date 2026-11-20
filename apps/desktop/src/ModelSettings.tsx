import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { request } from "./api";

export type ModelParameters = {
  temperature: number | null;
  top_p: number | null;
  max_output_tokens?: number | null;
  capabilities?: {
    max_output_tokens: number | null;
    context_window: number | null;
    document_input?: "text" | "pdf" | "image";
    multimodal?: boolean;
    document_transport?: "none" | "chat_file" | "chat_images";
    source: string;
  };
  reasoning_effort:
    "none" | "minimal" | "low" | "medium" | "high" | "xhigh" | "max" | null;
  timeout_seconds: number;
  document_timeout_seconds?: number;
  document_total_timeout_seconds?: number;
  json_mode: boolean;
};

export type ModelConnection = {
  id: string;
  name: string;
  provider: "openai" | "compatible" | "local";
  base_url: string;
  has_api_key: boolean;
  updated_at?: string;
};

export type ModelProfile = {
  id: string;
  name: string;
  connection_id: string | null;
  connection_name?: string | null;
  provider: "openai" | "compatible" | "local" | "mock";
  base_url: string;
  model: string;
  parameters: ModelParameters;
  has_api_key: boolean;
};

export type GlobalModels = {
  connections: ModelConnection[];
  profiles: ModelProfile[];
  roles: {
    extraction: string | null;
    reasoning: string | null;
    document_parse?: string | null;
    knowledge_extract?: string | null;
    knowledge_connect?: string | null;
  };
};

type ProviderKind = ModelConnection["provider"];
type ProviderTab = "common" | "custom";
type ModelDraft = {
  id?: string;
  model: string;
  name: string;
  parameters?: ModelParameters;
};

type ProviderPreset = {
  id: string;
  name: string;
  description: string;
  provider: ProviderKind;
  baseUrl: string;
  model: string;
  badge?: string;
};

const PROVIDER_PRESETS: ProviderPreset[] = [
  {
    id: "deepseek",
    name: "DeepSeek",
    description: "DeepSeek 官方兼容接口",
    provider: "compatible",
    baseUrl: "https://api.deepseek.com/v1",
    model: "deepseek-chat",
  },
  {
    id: "openai",
    name: "OpenAI",
    description: "OpenAI 官方接口",
    provider: "openai",
    baseUrl: "https://api.openai.com/v1",
    model: "gpt-4o-mini",
  },
  {
    id: "openrouter",
    name: "OpenRouter",
    description: "聚合多家模型的兼容接口",
    provider: "compatible",
    baseUrl: "https://openrouter.ai/api/v1",
    model: "openai/gpt-4o-mini",
  },
  {
    id: "siliconflow",
    name: "SiliconFlow",
    description: "硅基流动兼容接口",
    provider: "compatible",
    baseUrl: "https://api.siliconflow.cn/v1",
    model: "deepseek-ai/DeepSeek-V3",
  },
  {
    id: "zhipu",
    name: "智谱 AI",
    description: "GLM 系列兼容接口",
    provider: "compatible",
    baseUrl: "https://open.bigmodel.cn/api/paas/v4",
    model: "glm-4-flash",
  },
  {
    id: "dashscope",
    name: "通义千问",
    description: "DashScope 兼容接口",
    provider: "compatible",
    baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1",
    model: "qwen-plus",
  },
  {
    id: "ollama",
    name: "Ollama",
    description: "本机 Ollama 兼容接口",
    provider: "local",
    baseUrl: "http://127.0.0.1:11434/v1",
    model: "llama3.2",
    badge: "本地",
  },
];

const defaults: ModelParameters = {
  temperature: null,
  top_p: null,
  reasoning_effort: null,
  timeout_seconds: 90,
  document_timeout_seconds: 600,
  document_total_timeout_seconds: 1800,
  json_mode: true,
};

function visualPlanEndpoint(base: string): boolean {
  try {
    const url = new URL(base);
    const path = url.pathname.replace(/\/+$/, "");
    return (
      (url.hostname === "ark.cn-beijing.volces.com" &&
        path === "/api/plan/v3") ||
      (url.hostname === "tokenhub.tencentmaas.com" && path === "/plan/v3")
    );
  } catch {
    return false;
  }
}

function validDocumentTimeouts(parameters?: ModelParameters): boolean {
  const wait = parameters?.document_timeout_seconds ?? 600;
  const total = parameters?.document_total_timeout_seconds ?? 1800;
  return (
    Number.isInteger(wait) &&
    wait >= 30 &&
    wait <= 1800 &&
    Number.isInteger(total) &&
    total >= 60 &&
    total <= 3600 &&
    total >= wait
  );
}

function providerLabel(provider: ProviderKind) {
  if (provider === "openai") return "官方接口";
  if (provider === "local") return "本地接口";
  return "兼容接口";
}

function presetForConnection(connection: ModelConnection) {
  return PROVIDER_PRESETS.find(
    (preset) =>
      preset.baseUrl === connection.base_url ||
      connection.name.toLowerCase().includes(preset.name.toLowerCase()),
  );
}

const providerIdStorageKey = "researchgraph.model-provider-ids";

function providerIdsFromStorage(): Record<string, string> {
  try {
    const raw = localStorage.getItem(providerIdStorageKey);
    const parsed = raw ? JSON.parse(raw) : {};
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

function providerIdForConnection(
  connection: ModelConnection,
  preset?: ProviderPreset,
) {
  if (preset) return preset.id;
  return (
    providerIdsFromStorage()[connection.id] ??
    connection.name
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "")
  );
}

type ProviderPayload = {
  connection: {
    name: string;
    provider: ProviderKind;
    base_url: string;
    clear_key: boolean;
    api_key?: string;
    provider_id?: string;
  };
  models: ModelDraft[];
};

export function ModelSettings({ connected }: { connected: boolean }) {
  const client = useQueryClient();
  const route = "/api/v1/settings";
  const settings = useQuery({
    queryKey: ["model-settings"],
    queryFn: () => request<GlobalModels>("GET", route + "/models"),
    enabled: connected,
  });
  const [editingConnection, setEditingConnection] =
    useState<ModelConnection | null>(null);
  const [editorOpen, setEditorOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const connections = settings.data?.connections ?? [];
  const profiles = settings.data?.profiles ?? [];

  async function refresh() {
    await client.invalidateQueries({ queryKey: ["model-settings"] });
  }

  async function saveProvider(payload: ProviderPayload) {
    setBusy(true);
    setNotice("");
    setError("");
    try {
      const path = editingConnection
        ? route + "/connections/" + editingConnection.id + "/update"
        : route + "/connections";
      const { provider_id, ...connectionBody } = payload.connection;
      const saved = await request<ModelConnection>(
        "POST",
        path,
        connectionBody,
      );
      if (provider_id) {
        const providerIds = providerIdsFromStorage();
        providerIds[saved.id] = provider_id;
        localStorage.setItem(providerIdStorageKey, JSON.stringify(providerIds));
      }
      const existing = editingConnection
        ? profiles.filter(
            (profile) => profile.connection_id === editingConnection.id,
          )
        : [];
      const nextIds = new Set(
        payload.models.filter((model) => model.id).map((model) => model.id),
      );
      for (const profile of existing) {
        if (!nextIds.has(profile.id)) {
          await request("POST", route + "/models/" + profile.id + "/delete");
        }
      }
      for (const model of payload.models) {
        const modelBody = {
          name: model.name.trim() || model.model.trim(),
          connection_id: saved.id,
          model: model.model.trim(),
          parameters: { ...defaults, ...model.parameters },
        };
        if (model.id) {
          await request(
            "POST",
            route + "/models/" + model.id + "/update",
            modelBody,
          );
        } else {
          await request("POST", route + "/models", modelBody);
        }
      }
      await refresh();
      setNotice(saved.name + " 已保存，模型目录已更新。");
      setEditorOpen(false);
      setEditingConnection(null);
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "保存模型提供商失败",
      );
    } finally {
      setBusy(false);
    }
  }

  async function testProfile(profile: ModelProfile) {
    setBusy(true);
    setNotice("");
    setError("");
    try {
      const result = await request<{
        connected?: boolean;
        valid_json?: boolean;
      }>("POST", route + "/models/" + profile.id + "/test");
      setNotice(
        result.connected
          ? "连接成功，固定 JSON 校验" +
              (result.valid_json ? "通过" : "未通过") +
              "。这只验证接口可用性，不代表论文概览质量已验证。"
          : "连接未通过，请检查配置。",
      );
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "模型连接测试失败",
      );
    } finally {
      setBusy(false);
    }
  }

  async function deleteConnection(connection: ModelConnection) {
    if (
      !window.confirm(
        "删除模型提供商“" + connection.name + "”？已有用量和历史记录会保留。",
      )
    ) {
      return;
    }
    setBusy(true);
    setNotice("");
    setError("");
    try {
      await request(
        "POST",
        route + "/connections/" + connection.id + "/delete",
      );
      await refresh();
      setNotice(connection.name + " 已删除。");
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "删除模型提供商失败",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="model-settings" aria-label="全局模型设置">
      <div className="model-settings-heading">
        <div>
          <h2>模型</h2>
          <p>
            填入各提供商的 API
            密钥即可使用对应模型。连接信息集中保存，模型配置只选择模型与阅读参数。
          </p>
        </div>
        <span className="model-count">{connections.length} 个提供商</span>
      </div>
      {settings.error && <p role="alert">无法读取模型配置，请重试。</p>}
      <div className="provider-list" aria-label="模型提供商列表">
        {connections.map((connection) => {
          const connectionProfiles = profiles.filter(
            (profile) => profile.connection_id === connection.id,
          );
          return (
            <ProviderCard
              key={connection.id}
              connection={connection}
              profiles={connectionProfiles}
              preset={presetForConnection(connection)}
              busy={busy || !connected}
              onEdit={() => {
                setEditingConnection(connection);
                setEditorOpen(true);
              }}
              onDelete={() => void deleteConnection(connection)}
              onTest={(profile) => void testProfile(profile)}
            />
          );
        })}
        <button
          className="provider-add-card"
          disabled={!connected || busy}
          onClick={() => {
            setEditingConnection(null);
            setEditorOpen(true);
          }}
        >
          <span className="provider-add-icon">+</span>
          添加模型提供商
        </button>
      </div>
      <section className="model-role-panel" aria-label="阅读任务模型选择">
        <div>
          <h3>阅读任务模型</h3>
          <p>
            分别选择论文解析、概览和阅读辅助模型。论文解析需要该端点与模型支持
            PDF 文件输入，联网授权不等于文件能力。
          </p>
        </div>
        <div className="model-role-grid">
          {(
            [
              "document_parse",
              "extraction",
              "reasoning",
              "knowledge_extract",
              "knowledge_connect",
            ] as const
          ).map((role) => (
            <label key={role}>
              {role === "document_parse"
                ? "论文解析模型"
                : role === "knowledge_extract"
                  ? "论文知识建模模型"
                  : role === "knowledge_connect"
                    ? "跨论文联系分析模型"
                    : role === "extraction"
                      ? "论文概览模型"
                      : "章节精读与问答模型"}
              <select
                value={settings.data?.roles[role] ?? ""}
                disabled={!connected || busy}
                onChange={async (event) => {
                  setBusy(true);
                  setNotice("");
                  setError("");
                  try {
                    await request("POST", route + "/model-roles", {
                      ...(settings.data?.roles ?? {}),
                      [role]: event.target.value || null,
                    });
                    await refresh();
                    setNotice("阅读任务模型已更新。");
                  } catch (requestError) {
                    setError(
                      requestError instanceof Error
                        ? requestError.message
                        : "保存任务模型失败",
                    );
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                <option value="">未选择</option>
                {profiles
                  .filter((profile) => profile.provider !== "mock")
                  .map((profile) => (
                    <option key={profile.id} value={profile.id}>
                      {profile.name} · {profile.model}
                      {role === "document_parse"
                        ? profile.parameters.capabilities?.document_input !==
                            "text" &&
                          profile.parameters.capabilities?.document_input &&
                          ["chat_file", "chat_images"].includes(
                            profile.parameters.capabilities
                              ?.document_transport ?? "none",
                          )
                          ? " · 已声明 PDF 输入"
                          : " · 未声明 PDF 输入"
                        : ""}
                    </option>
                  ))}
              </select>
            </label>
          ))}
        </div>
        <p>
          编辑提供商，在每个模型下声明 PDF
          输入与文件传输方式。连接测试只验证文本 JSON，不验证 PDF
          能力；不支持文件的模型请使用本地解析。
        </p>
      </section>
      {editorOpen && (
        <ProviderEditor
          connection={editingConnection}
          profiles={profiles.filter(
            (profile) => profile.connection_id === editingConnection?.id,
          )}
          disabled={busy || !connected}
          onCancel={() => {
            setEditorOpen(false);
            setEditingConnection(null);
          }}
          onSave={saveProvider}
        />
      )}
      {notice && (
        <p role="status" className="settings-notice">
          {notice}
        </p>
      )}
      {error && (
        <p role="alert" className="error-text">
          {error}
        </p>
      )}
    </section>
  );
}

function ProviderCard({
  connection,
  profiles,
  preset,
  busy,
  onEdit,
  onDelete,
  onTest,
}: {
  connection: ModelConnection;
  profiles: ModelProfile[];
  preset?: ProviderPreset;
  busy: boolean;
  onEdit: () => void;
  onDelete: () => void;
  onTest: (profile: ModelProfile) => void;
}) {
  return (
    <article className="provider-card">
      <div className="provider-card-main">
        <div className="provider-card-title">
          <strong>{connection.name}</strong>
          {preset ? (
            <span className="provider-badge">{preset.badge ?? "预设"}</span>
          ) : (
            <span className="provider-badge">自定义</span>
          )}
          <span
            className={
              "provider-status-dot" +
              (connection.has_api_key || connection.provider === "local"
                ? " ready"
                : "")
            }
            aria-label={
              connection.has_api_key || connection.provider === "local"
                ? "已配置"
                : "未配置密钥"
            }
          />
        </div>
        <p>{connection.base_url}</p>
        <small>
          {providerLabel(connection.provider)} · {profiles.length} 个模型
          {connection.has_api_key ? " · 密钥已安全保存" : " · 尚未保存密钥"}
        </small>
        {profiles.length > 0 && (
          <div className="provider-model-summary">
            {profiles.map((profile) => (
              <span key={profile.id} title={profile.model}>
                {profile.name || profile.model}
              </span>
            ))}
          </div>
        )}
      </div>
      <div className="provider-card-actions">
        <button
          className="button secondary compact"
          disabled={busy}
          onClick={onEdit}
        >
          编辑
        </button>
        {profiles[0] && (
          <button
            className="text-button"
            disabled={busy}
            onClick={() => onTest(profiles[0])}
          >
            测试连接
          </button>
        )}
        <button
          className="text-button danger"
          disabled={busy}
          onClick={onDelete}
        >
          删除
        </button>
      </div>
    </article>
  );
}

function ProviderEditor({
  connection,
  profiles,
  disabled,
  onSave,
  onCancel,
}: {
  connection: ModelConnection | null;
  profiles: ModelProfile[];
  disabled: boolean;
  onSave: (payload: ProviderPayload) => Promise<void>;
  onCancel: () => void;
}) {
  const initialPreset = connection
    ? presetForConnection(connection)
    : PROVIDER_PRESETS[0];
  const [tab, setTab] = useState<ProviderTab>(
    connection && !initialPreset ? "custom" : "common",
  );
  const [selectedPreset, setSelectedPreset] = useState(
    initialPreset?.id ?? "deepseek",
  );
  const [providerId, setProviderId] = useState(
    connection
      ? providerIdForConnection(connection, initialPreset)
      : (initialPreset?.id ?? ""),
  );
  const [name, setName] = useState(
    connection?.name ?? initialPreset?.name ?? "",
  );
  const [provider, setProvider] = useState<ProviderKind>(
    connection?.provider ?? initialPreset?.provider ?? "compatible",
  );
  const [base, setBase] = useState(
    connection?.base_url ?? initialPreset?.baseUrl ?? "",
  );
  const [key, setKey] = useState("");
  const [clear, setClear] = useState(false);
  const [protocol, setProtocol] = useState("openai_chat_completions");
  const [models, setModels] = useState<ModelDraft[]>(
    profiles.length > 0
      ? profiles.map((profile) => ({
          id: profile.id,
          model: profile.model,
          name: profile.name,
          parameters: profile.parameters,
        }))
      : initialPreset
        ? [{ model: initialPreset.model, name: initialPreset.model }]
        : [{ model: "", name: "" }],
  );
  const chosenPreset = useMemo(
    () => PROVIDER_PRESETS.find((preset) => preset.id === selectedPreset),
    [selectedPreset],
  );

  function selectPreset(preset: ProviderPreset) {
    setSelectedPreset(preset.id);
    setProviderId(preset.id);
    setName(preset.name);
    setProvider(preset.provider);
    setBase(preset.baseUrl);
    if (!connection) setModels([{ model: preset.model, name: preset.model }]);
  }

  function addModel() {
    setModels((current) => [...current, { model: "", name: "" }]);
  }

  function updateModel(index: number, field: "model" | "name", value: string) {
    setModels((current) =>
      current.map((model, currentIndex) =>
        currentIndex === index ? { ...model, [field]: value } : model,
      ),
    );
  }

  function updateDocumentCapability(
    index: number,
    patch: Partial<NonNullable<ModelParameters["capabilities"]>>,
  ) {
    setModels((current) =>
      current.map((model, currentIndex) =>
        currentIndex === index
          ? {
              ...model,
              parameters: {
                ...(model.parameters ?? defaults),
                capabilities: {
                  max_output_tokens: null,
                  context_window: null,
                  document_input: "text",
                  multimodal: false,
                  document_transport: "none",
                  ...model.parameters?.capabilities,
                  ...patch,
                  source: "user_declared",
                },
              },
            }
          : model,
      ),
    );
  }

  function updateParameters(index: number, patch: Partial<ModelParameters>) {
    setModels((current) =>
      current.map((model, currentIndex) =>
        currentIndex === index
          ? {
              ...model,
              parameters: { ...defaults, ...model.parameters, ...patch },
            }
          : model,
      ),
    );
  }

  function applyVisualParsing(index: number) {
    setModels((current) =>
      current.map((model, currentIndex) =>
        currentIndex === index
          ? {
              ...model,
              parameters: {
                ...defaults,
                ...model.parameters,
                document_timeout_seconds: 600,
                document_total_timeout_seconds: 1800,
                reasoning_effort: "none",
                capabilities: {
                  max_output_tokens: null,
                  context_window: null,
                  ...model.parameters?.capabilities,
                  document_input: "image",
                  multimodal: true,
                  document_transport: "chat_images",
                  source: "user_declared",
                },
              },
            }
          : model,
      ),
    );
  }

  function removeModel(index: number) {
    setModels((current) =>
      current.filter((_, currentIndex) => currentIndex !== index),
    );
  }

  return (
    <div className="provider-modal-backdrop" role="presentation">
      <section
        className="provider-modal"
        role="dialog"
        aria-modal="true"
        aria-label={connection ? "编辑模型提供商" : "添加模型提供商"}
      >
        <div className="provider-modal-header">
          <div>
            <div className="eyebrow">MODEL PROVIDER</div>
            <h3>{connection ? "编辑模型提供商" : "添加模型提供商"}</h3>
            <p>连接信息只保存一次，后续可以在同一提供商下管理多个模型。</p>
          </div>
          <button className="modal-close" onClick={onCancel} aria-label="关闭">
            ×
          </button>
        </div>
        <div className="provider-tabs" role="tablist" aria-label="提供商类型">
          <button
            role="tab"
            aria-selected={tab === "common"}
            className={tab === "common" ? "active" : ""}
            onClick={() => setTab("common")}
          >
            第三方模型提供商
          </button>
          <button
            role="tab"
            aria-selected={tab === "custom"}
            className={tab === "custom" ? "active" : ""}
            onClick={() => {
              setTab("custom");
              setProvider("compatible");
            }}
          >
            自定义模型 API
          </button>
        </div>
        {tab === "common" && (
          <div className="provider-preset-grid">
            {PROVIDER_PRESETS.map((preset) => (
              <button
                key={preset.id}
                className={
                  "provider-preset" +
                  (selectedPreset === preset.id ? " selected" : "")
                }
                onClick={() => selectPreset(preset)}
              >
                <span className="provider-preset-mark">
                  {preset.name.slice(0, 1)}
                </span>
                <span>
                  <strong>{preset.name}</strong>
                  <small>{preset.description}</small>
                </span>
              </button>
            ))}
          </div>
        )}
        <div className="provider-form-scroll">
          {tab === "custom" && (
            <>
              <label>
                Provider ID
                <input
                  aria-label="Provider ID"
                  value={providerId}
                  onChange={(event) => setProviderId(event.target.value)}
                  placeholder="acme-gateway"
                  pattern="[a-z][a-z0-9_-]*"
                  title="使用小写字母开头的标识"
                  required
                />
                <small>用于区分提供商的短标识，不会进入 API Key 或日志。</small>
              </label>
              <label>
                显示名称
                <input
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  placeholder="我的模型网关"
                  required
                />
              </label>
            </>
          )}
          {tab === "common" && (
            <label>
              显示名称
              <input
                value={name}
                onChange={(event) => setName(event.target.value)}
                required
              />
            </label>
          )}
          <label>
            API 地址
            <input
              type="url"
              value={base}
              onChange={(event) => setBase(event.target.value)}
              placeholder="https://gateway.example/v1"
              required
            />
          </label>
          <label>
            API 协议
            <select
              value={protocol}
              onChange={(event) => setProtocol(event.target.value)}
            >
              <option value="openai_chat_completions">
                OpenAI Chat Completions
              </option>
            </select>
            <small>
              当前运行引擎使用兼容的 Chat Completions 接口；暂不宣称原生
              Anthropic 协议支持。
            </small>
          </label>
          <label>
            API 密钥
            <input
              aria-label="API 密钥"
              type="password"
              autoComplete="new-password"
              spellCheck={false}
              value={key}
              placeholder={
                connection?.has_api_key
                  ? "留空保留已有密钥"
                  : provider === "local"
                    ? "本地服务可留空"
                    : "输入 API 密钥"
              }
              onChange={(event) => setKey(event.target.value)}
            />
            <small>
              密钥只写入系统凭据存储，不进入 SQLite、浏览器缓存或日志。
            </small>
          </label>
          {connection?.has_api_key && (
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={clear}
                onChange={(event) => setClear(event.target.checked)}
              />
              清除当前密钥
            </label>
          )}
          <div className="model-directory-heading">
            <div>
              <h4>模型目录</h4>
              <p>手动维护模型 ID，保存后即可在阅读任务模型中选择。</p>
            </div>
            <button type="button" className="text-button" onClick={addModel}>
              + 添加模型
            </button>
          </div>
          <div className="model-directory" aria-label="模型目录">
            {models.map((model, index) => (
              <div key={model.id ?? "new-" + index}>
                <div className="model-directory-row">
                  <span className="model-drag-handle" aria-hidden="true">
                    ≡
                  </span>
                  <input
                    aria-label={"模型 ID " + (index + 1)}
                    placeholder="模型 ID"
                    value={model.model}
                    onChange={(event) =>
                      updateModel(index, "model", event.target.value)
                    }
                    required
                  />
                  <input
                    aria-label={"模型显示名称 " + (index + 1)}
                    placeholder="显示名称"
                    value={model.name}
                    onChange={(event) =>
                      updateModel(index, "name", event.target.value)
                    }
                    required
                  />
                  <button
                    type="button"
                    className="model-remove"
                    aria-label={"删除模型 " + (index + 1)}
                    onClick={() => removeModel(index)}
                    disabled={models.length === 1}
                  >
                    ×
                  </button>
                </div>
                <fieldset disabled={disabled}>
                  <legend>{"模型 " + (index + 1) + " 文档能力"}</legend>
                  <label>
                    PDF / 文档输入
                    <select
                      aria-label={"文档输入能力 " + (index + 1)}
                      value={
                        model.parameters?.capabilities?.document_input ?? "text"
                      }
                      onChange={(event) => {
                        const input = event.target.value as
                          "text" | "pdf" | "image";
                        updateDocumentCapability(index, {
                          document_input: input,
                          multimodal: input === "image",
                          document_transport:
                            input === "text"
                              ? "none"
                              : input === "image"
                                ? "chat_images"
                                : "chat_file",
                        });
                      }}
                    >
                      <option value="text">仅文本 / 未声明 PDF 能力</option>
                      <option value="pdf">支持直接 PDF 文件输入</option>
                      <option value="image">
                        支持图片理解，可识别 PDF 页面
                      </option>
                    </select>
                  </label>
                  <label>
                    文件传输方式
                    <select
                      aria-label={"文件传输方式 " + (index + 1)}
                      value={
                        model.parameters?.capabilities?.document_transport ??
                        "none"
                      }
                      disabled={
                        (model.parameters?.capabilities?.document_input ??
                          "text") === "text"
                      }
                      onChange={(event) =>
                        updateDocumentCapability(index, {
                          document_transport: event.target.value as
                            "none" | "chat_file" | "chat_images",
                          ...(event.target.value === "chat_images"
                            ? { document_input: "image", multimodal: true }
                            : {}),
                        })
                      }
                    >
                      <option value="none">未声明文件传输</option>
                      <option value="chat_file">
                        Chat Completions 文件内容（chat_file）
                      </option>
                      <option value="chat_images">
                        PDF 页面转图片（适用于视觉模型）
                      </option>
                    </select>
                  </label>
                  <label>
                    文档等待超时（秒）
                    <input
                      type="number"
                      aria-label={"文档等待超时 " + (index + 1)}
                      min={30}
                      max={1800}
                      step={1}
                      value={model.parameters?.document_timeout_seconds ?? 600}
                      onChange={(event) =>
                        updateParameters(index, {
                          document_timeout_seconds: Number(event.target.value),
                        })
                      }
                    />
                  </label>
                  <label>
                    文档解析总时限（秒）
                    <input
                      type="number"
                      aria-label={"文档解析总时限 " + (index + 1)}
                      min={60}
                      max={3600}
                      step={1}
                      value={
                        model.parameters?.document_total_timeout_seconds ?? 1800
                      }
                      onChange={(event) =>
                        updateParameters(index, {
                          document_total_timeout_seconds: Number(
                            event.target.value,
                          ),
                        })
                      }
                    />
                  </label>
                  {!validDocumentTimeouts(model.parameters) && (
                    <p role="alert">
                      等待超时须为 30–1800 秒；总时限须为 60–3600
                      秒，且不小于等待超时。
                    </p>
                  )}
                  <label>
                    推理强度
                    <select
                      aria-label={"推理强度 " + (index + 1)}
                      value={model.parameters?.reasoning_effort ?? ""}
                      onChange={(event) =>
                        updateParameters(index, {
                          reasoning_effort:
                            (event.target
                              .value as ModelParameters["reasoning_effort"]) ||
                            null,
                        })
                      }
                    >
                      <option value="">使用默认适配配置</option>
                      <option value="none">none（关闭推理，需端点支持）</option>
                      <option value="minimal">minimal</option>
                      <option value="low">low</option>
                      <option value="medium">medium</option>
                      <option value="high">high</option>
                      <option value="xhigh">xhigh</option>
                      <option value="max">max</option>
                    </select>
                  </label>
                  {visualPlanEndpoint(base) && (
                    <div>
                      <p>
                        此套餐端点的视觉模型建议使用 PDF 页面图片输入。
                        请先确认所选模型支持图片；文件格式与实际解析质量仍需验证。
                      </p>
                      <button
                        type="button"
                        className="button secondary"
                        onClick={() => applyVisualParsing(index)}
                        aria-label={"应用推荐解析配置 " + (index + 1)}
                      >
                        应用推荐解析配置
                      </button>
                      <small>
                        选择页面转图片，等待 600 秒、总时限 1800
                        秒，推理强度设为 none（关闭推理，需端点支持）。
                      </small>
                    </div>
                  )}
                  <small>
                    页面转图片仅在本地渲染页面，正文、公式和表格由模型识别。
                    能力声明和文本连接测试不能证明文件兼容性。
                    保存设置后请在论文页选择“使用模型重新解析”；旧任务重试沿用旧配置。
                    文档超时独立于普通文字任务；推理强度用于该模型的全部新任务。
                  </small>
                </fieldset>
              </div>
            ))}
          </div>
        </div>
        <div className="provider-modal-footer">
          <button
            className="button secondary"
            disabled={disabled}
            onClick={onCancel}
          >
            取消
          </button>
          <button
            className="button primary"
            disabled={
              disabled ||
              !name.trim() ||
              !base.trim() ||
              models.some(
                (model) =>
                  !model.model.trim() ||
                  !validDocumentTimeouts(model.parameters),
              )
            }
            onClick={() =>
              void onSave({
                connection: {
                  name: name.trim(),
                  provider,
                  base_url: base.trim(),
                  clear_key: clear,
                  provider_id: providerId.trim() || undefined,
                  ...(key.trim() ? { api_key: key.trim() } : {}),
                },
                models,
              })
            }
          >
            {connection ? "保存提供商" : "创建提供商"}
          </button>
        </div>
        {tab === "common" && chosenPreset && (
          <p className="provider-preset-note">
            已选择 {chosenPreset.name} 预设，可继续修改地址和模型 ID。
          </p>
        )}
      </section>
    </div>
  );
}

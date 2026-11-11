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
    source: string;
  };
  reasoning_effort:
    "none" | "minimal" | "low" | "medium" | "high" | "xhigh" | "max" | null;
  timeout_seconds: number;
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
  roles: { extraction: string | null; reasoning: string | null };
};

type ProviderKind = ModelConnection["provider"];
type ProviderTab = "common" | "custom";
type ModelDraft = { id?: string; model: string; name: string };

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
  json_mode: true,
};

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
          parameters: defaults,
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
            为论文概览和阅读辅助分别选择已配置的模型。选择不会再次要求 API
            地址或密钥。
          </p>
        </div>
        <div className="model-role-grid">
          {(["extraction", "reasoning"] as const).map((role) => (
            <label key={role}>
              {role === "extraction" ? "论文概览模型" : "章节精读与问答模型"}
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
                    </option>
                  ))}
              </select>
            </label>
          ))}
        </div>
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

  function updateModel(index: number, field: keyof ModelDraft, value: string) {
    setModels((current) =>
      current.map((model, currentIndex) =>
        currentIndex === index ? { ...model, [field]: value } : model,
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
              <div
                className="model-directory-row"
                key={model.id ?? "new-" + index}
              >
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
              models.some((model) => !model.model.trim())
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

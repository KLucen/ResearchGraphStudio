import { useState } from "react";
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
    "none" | "minimal" | "low" | "medium" | "high" | "xhigh" | null;
  timeout_seconds: number;
  json_mode: boolean;
};
export type ModelProfile = {
  id: string;
  name: string;
  provider: "openai" | "compatible" | "local" | "mock";
  base_url: string;
  model: string;
  parameters: ModelParameters;
  has_api_key: boolean;
};
export type GlobalModels = {
  profiles: ModelProfile[];
  roles: { extraction: string | null; reasoning: string | null };
};
const defaults: ModelParameters = {
  temperature: null,
  top_p: null,

  reasoning_effort: null,
  timeout_seconds: 90,
  json_mode: true,
};

export function ModelSettings({ connected }: { connected: boolean }) {
  const client = useQueryClient();
  const route = "/api/v1/settings";
  const settings = useQuery({
    queryKey: ["model-settings"],
    queryFn: () => request<GlobalModels>("GET", `${route}/models`),
    enabled: connected,
  });
  const [editing, setEditing] = useState<ModelProfile | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  async function action(path: string, body?: unknown) {
    setBusy(true);
    setNotice("");
    try {
      const result = await request<{
        connected?: boolean;
        valid_json?: boolean;
        mock?: boolean;
      }>("POST", path, body);
      setNotice(
        result.connected
          ? `真实模型连接成功；JSON 校验${result.valid_json ? "通过" : "未通过"}`
          : "设置已保存",
      );
      await client.invalidateQueries({
        queryKey: ["model-settings"],
      });
      return true;
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "操作失败");
      return false;
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="model-settings" aria-label="全局模型设置">
      <h2>全局模型设置</h2>
      <p>
        API Key 保存在 Windows
        凭据管理器，所有项目共用这里的配置和默认模型。测试连接只发送固定测试文本；抽取和推理另行确认论文传输。
      </p>
      {settings.error && <p role="alert">无法读取模型配置，请重试。</p>}
      <div className="import-controls">
        {(["extraction", "reasoning"] as const).map((role) => (
          <label key={role}>
            {role === "extraction"
              ? "Extraction 抽取模型"
              : "Reasoning 推理模型"}
            <select
              value={settings.data?.roles[role] ?? ""}
              disabled={!connected || busy}
              onChange={(e) =>
                void action(`${route}/model-roles`, {
                  ...settings.data?.roles,
                  [role]: e.target.value || null,
                })
              }
            >
              <option value="">未选择</option>
              {settings.data?.profiles
                .filter((p) => p.provider !== "mock")
                .map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} · {p.model}
                  </option>
                ))}
            </select>
          </label>
        ))}
      </div>
      {settings.data?.profiles
        .filter((p) => p.provider !== "mock")
        .map((p) => (
          <article className="text-chunk" key={p.id}>
            <strong>
              {p.name} · {p.provider} · {p.model}
            </strong>
            <p>
              {p.base_url} · {p.has_api_key ? "密钥已安全保存" : "未保存密钥"}
            </p>
            <small>
              {p.parameters?.capabilities?.max_output_tokens
                ? `模型最大输出 ${p.parameters.capabilities.max_output_tokens.toLocaleString()} Tokens（自动）`
                : "输出上限：接口未提供，使用服务默认值"}
            </small>
            <button
              className="text-button"
              disabled={busy || !connected}
              onClick={() => setEditing(p)}
            >
              编辑 {p.name}
            </button>
            <button
              className="text-button"
              disabled={busy || !connected}
              onClick={() => void action(`${route}/models/${p.id}/test`)}
            >
              测试连接 {p.name}
            </button>
            <button
              className="text-button"
              disabled={busy || !connected}
              onClick={() => {
                if (
                  window.confirm(
                    `删除 ${p.name} 及其保存的密钥？已有知识和模型记录会保留。`,
                  )
                )
                  void action(`${route}/models/${p.id}/delete`);
              }}
            >
              删除 {p.name}
            </button>
          </article>
        ))}
      <ProfileEditor
        key={editing?.id ?? "new"}
        profile={editing}
        disabled={!connected || busy}
        onCancel={() => setEditing(null)}
        onSave={async (body) => {
          const ok = await action(
            `${route}/models${editing ? `/${editing.id}/update` : ""}`,
            body,
          );
          if (ok) setEditing(null);
          return ok;
        }}
      />
      {notice && <p role="status">{notice}</p>}
    </section>
  );
}

function ProfileEditor({
  profile,
  disabled,
  onSave,
  onCancel,
}: {
  profile: ModelProfile | null;
  disabled: boolean;
  onSave: (body: unknown) => Promise<boolean>;
  onCancel: () => void;
}) {
  const [name, setName] = useState(profile?.name ?? "");
  const [provider, setProvider] = useState<ModelProfile["provider"]>(
    profile?.provider ?? "compatible",
  );
  const [base, setBase] = useState(profile?.base_url ?? "");
  const [model, setModel] = useState(profile?.model ?? "");
  const [key, setKey] = useState("");
  const [clear, setClear] = useState(false);
  const [params, setParams] = useState(profile?.parameters ?? defaults);
  return (
    <form
      className="model-form"
      onSubmit={async (e) => {
        e.preventDefault();
        const body = {
          name,
          provider,
          base_url: provider === "mock" ? "" : base,
          model: provider === "mock" ? "offline-extractive-fixture-v1" : model,
          parameters: {
            ...params,
            max_output_tokens: null,
            capabilities: undefined,
          },
          clear_key: clear,
          ...(key && provider !== "mock" ? { api_key: key } : {}),
        };
        // Do not put secrets in query/mutation caches or browser storage.
        setKey("");
        const ok = await onSave(body);
        if (ok && !profile) {
          setName("");
          setModel("");
        }
      }}
    >
      <h3>{profile ? "编辑配置" : "新增模型配置"}</h3>
      <label>
        配置名称
        <input
          required
          maxLength={80}
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </label>
      <label>
        服务类型
        <select
          value={provider}
          onChange={(e) => {
            const value = e.target.value as ModelProfile["provider"];
            setProvider(value);
            setKey("");
            setBase(
              value === "openai"
                ? "https://api.openai.com/v1"
                : value === "local"
                  ? "http://127.0.0.1:8000/v1"
                  : "",
            );
          }}
        >
          <option value="openai">OpenAI</option>
          <option value="compatible">OpenAI-compatible API</option>
          <option value="local">本地模型</option>
        </select>
      </label>
      {provider !== "mock" && (
        <>
          <label>
            Base URL
            <input
              required
              type="url"
              autoComplete="off"
              value={base}
              onChange={(e) => setBase(e.target.value)}
            />
          </label>
          <label>
            Model ID
            <input
              required
              maxLength={150}
              value={model}
              onChange={(e) => setModel(e.target.value)}
            />
          </label>
          <label>
            API Key
            <input
              type="password"
              autoComplete="new-password"
              spellCheck={false}
              maxLength={2400}
              value={key}
              placeholder={
                profile?.has_api_key
                  ? "留空保留；更换端点须重新录入"
                  : "本地服务可留空"
              }
              onChange={(e) => setKey(e.target.value)}
            />
          </label>
          {profile?.has_api_key && (
            <label>
              <input
                type="checkbox"
                checked={clear}
                onChange={(e) => setClear(e.target.checked)}
              />
              清除当前密钥引用
            </label>
          )}
          <label>
            Temperature（留空使用服务默认）
            <input
              type="number"
              min={0}
              max={2}
              step={0.1}
              value={params.temperature ?? ""}
              onChange={(e) =>
                setParams({
                  ...params,
                  temperature:
                    e.target.value === "" ? null : Number(e.target.value),
                })
              }
            />
          </label>
          <label>
            Top P（留空使用默认）
            <input
              type="number"
              min={0.01}
              max={1}
              step={0.05}
              value={params.top_p ?? ""}
              onChange={(e) =>
                setParams({
                  ...params,
                  top_p: e.target.value === "" ? null : Number(e.target.value),
                })
              }
            />
          </label>
          <p className="quiet-note">
            输出预算由模型能力自动管理。
            {profile?.parameters.capabilities?.max_output_tokens
              ? `接口公布的最大输出：${profile.parameters.capabilities.max_output_tokens.toLocaleString()} Tokens。`
              : "接口未提供输出上限时使用服务默认值；可用测试连接刷新。"}
          </p>
          <label>
            超时（秒）
            <input
              type="number"
              min={5}
              max={180}
              value={params.timeout_seconds}
              onChange={(e) =>
                setParams({
                  ...params,
                  timeout_seconds: Number(e.target.value),
                })
              }
            />
          </label>
          <label>
            Reasoning effort
            <select
              value={params.reasoning_effort ?? ""}
              onChange={(e) =>
                setParams({
                  ...params,
                  reasoning_effort: (e.target.value ||
                    null) as ModelParameters["reasoning_effort"],
                })
              }
            >
              <option value="">服务默认</option>
              {["none", "minimal", "low", "medium", "high", "xhigh"].map(
                (v) => (
                  <option key={v}>{v}</option>
                ),
              )}
            </select>
          </label>
          <label>
            <input
              type="checkbox"
              checked={params.json_mode}
              onChange={(e) =>
                setParams({ ...params, json_mode: e.target.checked })
              }
            />
            请求 JSON Object 模式（服务需支持）
          </label>
        </>
      )}
      <div>
        <button className="button primary" disabled={disabled}>
          保存模型配置
        </button>
        {profile && (
          <button type="button" className="button secondary" onClick={onCancel}>
            取消编辑
          </button>
        )}
      </div>
    </form>
  );
}

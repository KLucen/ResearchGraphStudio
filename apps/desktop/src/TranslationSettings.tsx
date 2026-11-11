import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { invoke } from "@tauri-apps/api/core";
import { api, type TranslationLaunchMode } from "./api";

export function TranslationSettings({ connected }: { connected: boolean }) {
  const client = useQueryClient();
  const settings = useQuery({
    queryKey: ["translation-settings"],
    queryFn: api.translationSettings,
    enabled: connected,
  });
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [url, setUrl] = useState<string | null>(null);
  const [launchMode, setLaunchMode] = useState<TranslationLaunchMode | null>(
    null,
  );
  const [pythonPath, setPythonPath] = useState<string | null>(null);
  const [serverPath, setServerPath] = useState<string | null>(null);
  const pickFile = useMutation({
    mutationFn: async (kind: "python" | "server") => ({
      kind,
      path: await invoke<string | null>("choose_translation_runtime_file", {
        kind,
      }),
    }),
    onSuccess: ({ kind, path }) => {
      if (!path) return;
      if (kind === "python") setPythonPath(path);
      else setServerPath(path);
    },
  });
  const mode = launchMode ?? settings.data?.launch_mode ?? "bundled";
  const draft = {
    enabled: enabled ?? settings.data?.enabled ?? true,
    service_url: url ?? settings.data?.service_url ?? "http://127.0.0.1:8890",
    launch_mode: mode,
    python_path:
      (pythonPath ?? settings.data?.python_path ?? "").trim() || null,
    server_path:
      (serverPath ?? settings.data?.server_path ?? "").trim() || null,
  };
  const saved = {
    enabled: settings.data?.enabled ?? true,
    service_url: settings.data?.service_url ?? "http://127.0.0.1:8890",
    launch_mode: settings.data?.launch_mode ?? "bundled",
    python_path: settings.data?.python_path ?? null,
    server_path: settings.data?.server_path ?? null,
  };
  const unsaved = JSON.stringify(draft) !== JSON.stringify(saved);
  const check = useMutation({ mutationFn: api.checkTranslationService });
  const save = useMutation({
    mutationFn: () => api.saveTranslationSettings(draft),
    onSuccess: (value) => {
      client.setQueryData(["translation-settings"], value);
      check.reset();
    },
  });
  const error = save.error ?? check.error ?? pickFile.error ?? settings.error;
  return (
    <section
      className="settings-card translation-settings"
      aria-label="文献翻译服务"
    >
      <div className="settings-title">
        <h2>文献翻译服务</h2>
        <span className="pill">
          {mode === "bundled" ? "内置引擎" : "高级 · 外部服务"}
        </span>
      </div>
      <p>
        使用已保存的模型连接与 API 密钥，按原文排版生成双语对照或中文 PDF。
        内置引擎、字体和模型资源随安装包提供，提交翻译时按需启动。
      </p>
      <div className="translation-settings-form">
        <label className="translation-checkbox">
          <input
            type="checkbox"
            checked={draft.enabled}
            onChange={(event) => setEnabled(event.target.checked)}
          />
          启用文献翻译
        </label>
        <div className="translation-bundled-engine">
          <label className="translation-checkbox">
            <input
              type="radio"
              name="translation-launch-mode"
              checked={mode === "bundled"}
              onChange={() => setLaunchMode("bundled")}
            />
            内置翻译引擎（推荐）
          </label>
          <p className="muted">
            pdf2zh-next 2.10.2 · BabelDOC 0.7.1。无需配置 Python 或 Server
            路径。PDF 副本与译文保存在本地，原文件保持不变。
          </p>
        </div>
        <details className="translation-advanced">
          <summary>高级：外部翻译服务</summary>
          <div className="translation-advanced-body">
            <p className="muted">
              仅在使用自己维护的 zotero-pdf2zh Server 4.1.8 时配置。
              已有路径会保留，切回内置引擎无需重新填写。
            </p>
            <fieldset className="translation-mode-choice">
              <legend>外部服务运行方式</legend>
              <label className="translation-checkbox">
                <input
                  type="radio"
                  name="translation-launch-mode"
                  checked={mode === "managed"}
                  onChange={() => setLaunchMode("managed")}
                />
                外部服务自动启停
              </label>
              <label className="translation-checkbox">
                <input
                  type="radio"
                  name="translation-launch-mode"
                  checked={mode === "manual"}
                  onChange={() => setLaunchMode("manual")}
                />
                手动连接外部服务
              </label>
            </fieldset>
            {mode === "managed" && (
              <div className="translation-launch-paths">
                <label>
                  Python 解释器路径
                  <span className="translation-path-picker">
                    <input
                      type="text"
                      aria-label="Python 解释器路径"
                      value={pythonPath ?? settings.data?.python_path ?? ""}
                      placeholder="安装翻译环境的 python.exe 绝对路径"
                      onChange={(event) => setPythonPath(event.target.value)}
                    />
                    <button
                      type="button"
                      className="button secondary"
                      aria-label="选择 Python 解释器"
                      disabled={pickFile.isPending}
                      onClick={() => pickFile.mutate("python")}
                    >
                      浏览
                    </button>
                  </span>
                </label>
                <label>
                  Server 脚本路径
                  <span className="translation-path-picker">
                    <input
                      type="text"
                      aria-label="Server 脚本路径"
                      value={serverPath ?? settings.data?.server_path ?? ""}
                      placeholder="独立安装的 server.py 绝对路径"
                      onChange={(event) => setServerPath(event.target.value)}
                    />
                    <button
                      type="button"
                      className="button secondary"
                      aria-label="选择 Server 脚本"
                      disabled={pickFile.isPending}
                      onClick={() => pickFile.mutate("server")}
                    >
                      浏览
                    </button>
                  </span>
                </label>
                <p className="muted">
                  使用已安装翻译依赖的 Python
                  环境。提交非缓存翻译时启动，任务结束后关闭本应用启动的实例。
                </p>
              </div>
            )}
            {mode !== "bundled" && (
              <>
                <label className="translation-service-url">
                  本机服务地址
                  <input
                    type="url"
                    value={draft.service_url}
                    onChange={(event) => setUrl(event.target.value)}
                  />
                </label>
                <p className="muted">
                  {mode === "manual"
                    ? "请先独立启动服务，并确保仅供本应用独占使用。"
                    : "自动启动的专用服务仅供本应用使用。"}
                  外部服务会在自己的目录保留 PDF 副本与输出，请在该服务中管理。
                </p>
              </>
            )}
          </div>
        </details>
        <div className="translation-actions">
          <button
            className="button primary"
            disabled={!connected || settings.isPending || save.isPending}
            onClick={() => save.mutate()}
          >
            {save.isPending ? "正在保存…" : "保存翻译设置"}
          </button>
          <button
            className="button secondary"
            disabled={
              !connected ||
              settings.isPending ||
              unsaved ||
              save.isPending ||
              check.isPending
            }
            onClick={() => check.mutate()}
          >
            {check.isPending
              ? "正在检查…"
              : mode === "bundled"
                ? "检查内置引擎资源"
                : mode === "managed"
                  ? "检查启动配置"
                  : "检查已保存的服务"}
          </button>
        </div>
        <p className="muted">
          {mode === "bundled"
            ? "检查只核对内置运行文件、字体和模型资源，不启动引擎、不提交论文，也不调用模型。"
            : mode === "managed"
              ? "检查只验证已保存的启动配置，不启动服务，不提交论文，也不调用模型。"
              : "连接检查仅在点击后执行，不提交论文，也不调用模型。"}
          {unsaved && "请先保存设置再检查。"}
        </p>
        {save.isSuccess && <p role="status">翻译设置已保存。</p>}
        {check.data && !unsaved && (
          <p
            role="status"
            className={check.data.available ? "muted" : "quality-note"}
          >
            {mode === "bundled"
              ? check.data.available
                ? "运行文件与资源检查通过"
                : "内置引擎资源未就绪"
              : mode === "managed"
                ? check.data.available
                  ? "启动配置就绪"
                  : "启动配置未就绪"
                : check.data.available
                  ? "服务可用"
                  : "服务不可用"}{" "}
            · {check.data.message}
            {check.data.version ? ` · ${check.data.version}` : ""} · 活动任务{" "}
            {check.data.active_tasks}
          </p>
        )}
        {error && (
          <p role="alert" className="error-text">
            {error instanceof Error ? error.message : String(error)}
          </p>
        )}
      </div>
    </section>
  );
}

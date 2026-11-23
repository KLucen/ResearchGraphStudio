import { useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { invoke, isTauri } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";

type CloseBehavior = "hide_to_tray" | "exit";

const preferenceKey = ["desktop-close-behavior"];

export function WindowCloseSettings() {
  const desktop = isTauri();
  const client = useQueryClient();
  const preference = useQuery({
    queryKey: preferenceKey,
    queryFn: () => invoke<CloseBehavior | null>("desktop_close_behavior"),
    enabled: desktop,
  });
  const save = useMutation({
    mutationFn: (behavior: CloseBehavior) =>
      invoke<CloseBehavior>("set_desktop_close_behavior", { behavior }),
    onSuccess: (behavior) => client.setQueryData(preferenceKey, behavior),
  });

  useEffect(() => {
    if (!desktop) return;
    const subscription = listen<CloseBehavior>(
      "desktop-close-behavior-changed",
      ({ payload }) => client.setQueryData(preferenceKey, payload),
    );
    void subscription.catch(() => {});
    return () => {
      void subscription.then((unlisten) => unlisten()).catch(() => {});
    };
  }, [client, desktop]);

  if (!desktop) return null;

  return (
    <section className="settings-card" aria-labelledby="window-settings-title">
      <div className="settings-title">
        <h2 id="window-settings-title">桌面窗口</h2>
      </div>
      <label className="window-close-setting">
        关闭窗口时
        <select
          value={preference.data ?? ""}
          disabled={!preference.isSuccess || save.isPending}
          onChange={(event) => {
            const behavior = event.target.value;
            if (behavior === "hide_to_tray" || behavior === "exit") {
              save.mutate(behavior);
            }
          }}
        >
          <option value="" disabled>
            {preference.isPending ? "正在读取…" : "首次关闭时询问"}
          </option>
          <option value="hide_to_tray">隐藏到任务栏托盘</option>
          <option value="exit">退出主程序</option>
        </select>
      </label>
      <p>隐藏后可从任务栏托盘打开主窗口或退出主程序。</p>
      {preference.isError && (
        <div>
          <p role="alert" className="error-text">
            无法读取窗口关闭设置。
          </p>
          <button
            type="button"
            className="button secondary"
            disabled={preference.isFetching}
            onClick={() => void preference.refetch()}
          >
            重新读取设置
          </button>
        </div>
      )}
      {save.isError && (
        <div role="alert" className="error-text">
          无法保存窗口关闭设置，请重试。
        </div>
      )}
    </section>
  );
}

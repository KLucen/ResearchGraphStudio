import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ModelSettings } from "../src/ModelSettings";
import "../src/style.css";

declare global {
  interface Window {
    __documentSettingsCalls: { method: string; path: string; body: unknown }[];
  }
}
window.__documentSettingsCalls = [];
const connection = {
  id: "fixture-connection",
  name: "Synthetic Ark",
  provider: "compatible",
  base_url: "https://ark.cn-beijing.volces.com/api/plan/v3",
  has_api_key: true,
};
let profile = {
  id: "fixture-profile",
  project_id: null,
  connection_id: connection.id,
  provider: "compatible",
  base_url: connection.base_url,
  name: "Synthetic vision",
  model: "deepseek-v4.1-flash",
  has_api_key: true,
  parameters: {
    timeout_seconds: 90,
    text_timeout_policy: null as "activity" | "legacy" | null,
    reasoning_effort: "max",
    capabilities: {
      document_input: "image",
      multimodal: true,
      document_transport: "chat_file",
      source: "user_declared",
    },
  },
};
Object.defineProperty(window, "__TAURI_INTERNALS__", {
  value: {
    invoke: async (
      _command: string,
      args: { method: string; path: string; body: unknown },
    ) => {
      window.__documentSettingsCalls.push(args);
      if (args.method === "GET" && args.path === "/api/v1/settings/models")
        return {
          connections: [connection],
          profiles: [profile],
          roles: {
            document_parse: profile.id,
            extraction: null,
            reasoning: null,
          },
        };
      if (
        args.method === "POST" &&
        args.path === `/api/v1/settings/connections/${connection.id}/update`
      )
        return connection;
      if (
        args.method === "POST" &&
        args.path === `/api/v1/settings/models/${profile.id}/update`
      ) {
        profile = { ...profile, ...(args.body as typeof profile) };
        return profile;
      }
      throw new Error("Unexpected synthetic native request");
    },
  },
});
createRoot(document.getElementById("root")!).render(
  <QueryClientProvider
    client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
  >
    <main style={{ padding: 20 }}>
      <ModelSettings connected />
    </main>
  </QueryClientProvider>,
);

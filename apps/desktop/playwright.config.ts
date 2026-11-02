import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  workers: 1,
  use: {
    channel: "msedge",
    headless: true,
    viewport: { width: 1280, height: 900 },
    baseURL: "http://127.0.0.1:1427",
  },
  webServer: {
    command: "pnpm exec vite --host 127.0.0.1 --port 1427 --strictPort",
    url: "http://127.0.0.1:1427/e2e/graph.html",
    reuseExistingServer: false,
  },
});

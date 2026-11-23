import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "../src/App";
import { api } from "../src/api";
import { sidebarPapers, sidebarProjects } from "../src/sidebarFixtures";
import "../src/style.css";

declare global {
  interface Window {
    __sidebarViewedPapers: string[];
    __sidebarUnexpectedRequests: unknown[];
    __sidebarCreatedProjects: string[];
  }
}
window.__sidebarViewedPapers = [];
window.__sidebarUnexpectedRequests = [];
window.__sidebarCreatedProjects = [];
let projects = [...sidebarProjects];
api.host = async () => ({
  running: true,
  data_dir: "synthetic-sidebar-data",
  error: null,
});
api.health = async () =>
  ({
    status: "ok",
    version: "synthetic",
    schema_version: "synthetic",
    fts5: true,
  }) as never;
api.projects = async () => ({ items: projects, next_cursor: null });
api.jobs = async () => [];
api.jobsPage = async () => ({ items: [], next_cursor: null });
api.papers = async (id) => ({ items: sidebarPapers(id), next_cursor: null });
api.searchWorkspace = async (term, offset = 0) => {
  const items = projects
    .flatMap((project) => [
      {
        kind: "project" as const,
        id: project.id,
        title: project.name,
        project,
      },
      ...sidebarPapers(project.id).map((paper) => ({
        kind: "paper" as const,
        id: paper.id,
        title: paper.title,
        project,
      })),
    ])
    .filter((hit) => hit.title.includes(term));
  return {
    items: items.slice(offset, offset + 24),
    total: items.length,
    next_offset: offset + 24 < items.length ? offset + 24 : null,
  };
};
api.paper = async (id) => {
  window.__sidebarViewedPapers.push(id);
  const paper = projects
    .flatMap((project) => sidebarPapers(project.id))
    .find((item) => item.id === id)!;
  return { paper, revisions: [], sources: [] };
};
api.importSessions = async () => [];
api.createProject = async (body) => {
  const project = { ...sidebarProjects[0], ...body, id: "sidebar-created" };
  projects = [...projects, project];
  window.__sidebarCreatedProjects.push(project.name);
  return project;
};
Object.defineProperty(window, "__TAURI_INTERNALS__", {
  value: {
    invoke: async (_command: string, args: unknown) => {
      window.__sidebarUnexpectedRequests.push(args);
      throw new Error("Unexpected synthetic sidebar request");
    },
  },
});
createRoot(document.getElementById("root")!).render(
  <QueryClientProvider
    client={
      new QueryClient({
        defaultOptions: {
          queries: { retry: false },
          mutations: { retry: false },
        },
      })
    }
  >
    <App />
  </QueryClientProvider>,
);

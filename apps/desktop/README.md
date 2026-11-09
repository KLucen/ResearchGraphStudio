# ResearchGraph Studio Lite Desktop

Tauri 2 + React desktop client for the Lite local reading workflow.

## Active views

- Research projects and Lite project creation.
- Zotero collection/attachment selection and local PDF import.
- Paper list, chapter structure, text search and task history.
- Optional PaperCard + LightGraph overview with a single user-triggered model request.
- Model settings, token usage and local engine diagnostics.

The old GraphRAG, Query, Lint and Wiki screens are retired from the active Lite route. The reusable React Flow primitives remain under `src/ForceGraph.tsx`, `src/forceSimulation.ts`, `src/graphLayout.ts` and `src/graphAppearance.tsx`.

Run the web client with `pnpm --dir apps/desktop dev`; run the full Tauri host with `pnpm dev` after building the sidecar.

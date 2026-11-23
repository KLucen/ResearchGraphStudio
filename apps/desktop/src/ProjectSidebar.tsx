import { useEffect, useState } from "react";
import { useInfiniteQuery } from "@tanstack/react-query";
import {
  ArrowDown,
  ArrowRight,
  FileText,
  FolderOpen,
  Plus,
  Upload,
} from "lucide-react";
import { api, type Project } from "./api";
import { useContextMenu } from "./ContextMenu";

type SelectionHandlers = {
  onImport: (projectId: string) => void;
  onSelect: (project: Project, paperId: string | null) => void;
};

export function ProjectSidebar({
  connected,
  projects,
  selectedProjectId,
  selectedPaperId,
  onCreate,
  onImport,
  onSelect,
}: SelectionHandlers & {
  connected: boolean;
  projects: Project[];
  selectedProjectId: string | null;
  selectedPaperId: string | null;
  onCreate: () => void;
}) {
  const { contextMenuProps, contextMenu } = useContextMenu();
  const [expanded, setExpanded] = useState<Record<string, boolean>>(() => {
    try {
      const saved = JSON.parse(
        localStorage.getItem("rgs.sidebar.projects") ?? "{}",
      );
      if (saved && typeof saved === "object" && !Array.isArray(saved))
        return saved;
    } catch {
      // Opening a project does not require working browser storage.
    }
    return {};
  });

  useEffect(() => {
    try {
      localStorage.setItem("rgs.sidebar.projects", JSON.stringify(expanded));
    } catch {
      // Keep expansion available for the current session.
    }
  }, [expanded]);

  return (
    <div
      className="project-tree"
      role="region"
      aria-label="个人研究项目"
      tabIndex={0}
    >
      {projects.length === 0 ? (
        <button
          type="button"
          className="project-tree-empty"
          disabled={!connected}
          onClick={onCreate}
        >
          <Plus size={14} />
          新建研究项目
        </button>
      ) : (
        projects.map((project, index) => {
          const isSelected = selectedProjectId === project.id;
          const isOpen = expanded[project.id] ?? (isSelected || index === 0);
          return (
            <ProjectTreeGroup
              key={project.id}
              connected={connected}
              project={project}
              isOpen={isOpen}
              isSelected={isSelected}
              selectedPaperId={isSelected ? selectedPaperId : null}
              contextMenuProps={contextMenuProps}
              onToggle={() =>
                setExpanded((current) => ({
                  ...current,
                  [project.id]: !isOpen,
                }))
              }
              onImport={onImport}
              onSelect={onSelect}
            />
          );
        })
      )}
      {contextMenu}
    </div>
  );
}

function ProjectTreeGroup({
  connected,
  project,
  isOpen,
  isSelected,
  selectedPaperId,
  contextMenuProps,
  onToggle,
  onImport,
  onSelect,
}: SelectionHandlers & {
  connected: boolean;
  project: Project;
  isOpen: boolean;
  isSelected: boolean;
  selectedPaperId: string | null;
  contextMenuProps: ReturnType<typeof useContextMenu>["contextMenuProps"];
  onToggle: () => void;
}) {
  const query = useInfiniteQuery({
    queryKey: ["sidebar-papers", project.id],
    queryFn: ({ pageParam }) => api.papers(project.id, pageParam),
    initialPageParam: 0,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    enabled: connected,
    refetchInterval: isOpen ? 3000 : false,
  });
  const papers = [
    ...new Map(
      query.data?.pages.flatMap((page) =>
        page.items.map((paper) => [paper.id, paper] as const),
      ),
    ).values(),
  ];
  const total =
    query.data?.pages[0]?.total ??
    (query.isSuccess ? papers.length : undefined);

  return (
    <div className="project-tree-group">
      <div
        className={
          isSelected ? "project-tree-row selected" : "project-tree-row"
        }
      >
        <button
          type="button"
          className="project-tree-toggle"
          aria-label={isOpen ? `收起${project.name}` : `展开${project.name}`}
          aria-expanded={isOpen}
          onClick={onToggle}
        >
          {isOpen ? <ArrowDown size={13} /> : <ArrowRight size={13} />}
        </button>
        <button
          type="button"
          className="project-tree-project"
          title={project.name}
          aria-current={isSelected && !selectedPaperId ? "page" : undefined}
          {...contextMenuProps("研究项目操作", [
            { label: "打开项目", action: () => onSelect(project, null) },
            {
              label: "导入论文",
              disabled: !connected,
              action: () => onImport(project.id),
            },
            {
              label: isOpen ? "收起论文列表" : "展开论文列表",
              action: onToggle,
            },
          ])}
          onClick={() => onSelect(project, null)}
        >
          <FolderOpen size={14} />
          <span>{project.name}</span>
        </button>
        {isSelected && (
          <button
            type="button"
            className="project-tree-import"
            aria-label={`向${project.name}导入论文`}
            title={`向${project.name}导入论文`}
            onClick={() => onImport(project.id)}
          >
            <Upload size={12} />
          </button>
        )}
        {total !== undefined && (
          <span className="project-tree-count">{total}</span>
        )}
      </div>
      {isOpen && (
        <div className="project-tree-papers">
          {query.isPending && (
            <span className="project-tree-muted">
              {connected ? "读取论文…" : "等待连接引擎"}
            </span>
          )}
          {query.isError && (
            <div className="project-tree-muted" role="status">
              读取论文失败。{" "}
              <button
                type="button"
                className="text-button"
                onClick={() => void query.refetch()}
              >
                重新读取
              </button>
            </div>
          )}
          {query.isSuccess && !papers.length && (
            <span className="project-tree-muted">暂无论文</span>
          )}
          {papers.map((paper) => (
            <button
              type="button"
              className={
                selectedPaperId === paper.id
                  ? "project-tree-paper selected"
                  : "project-tree-paper"
              }
              key={paper.id}
              title={paper.title}
              aria-current={selectedPaperId === paper.id ? "page" : undefined}
              {...contextMenuProps("项目论文操作", [
                {
                  label: "打开论文阅读",
                  action: () => onSelect(project, paper.id),
                },
                {
                  label: "打开所属项目",
                  action: () => onSelect(project, null),
                },
              ])}
              onClick={() => onSelect(project, paper.id)}
            >
              <FileText size={13} />
              <span>{paper.title}</span>
            </button>
          ))}
          {query.hasNextPage && (
            <button
              type="button"
              className="text-button project-tree-muted"
              aria-label={`加载${project.name}的更多论文`}
              disabled={!connected || query.isFetching}
              onClick={() => void query.fetchNextPage()}
            >
              {query.isFetchingNextPage ? "加载论文…" : "加载更多论文"}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

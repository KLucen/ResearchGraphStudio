import { useEffect, useId, useRef, useState } from "react";
import { useInfiniteQuery } from "@tanstack/react-query";
import { BookOpen, FolderOpen, Search, X } from "lucide-react";
import { api, type WorkspaceSearchHit } from "./api";
import "./workspaceSearch.css";

export function WorkspaceSearchDialog({
  connected,
  onClose,
  onOpen,
}: {
  connected: boolean;
  onClose: () => void;
  onOpen: (hit: WorkspaceSearchHit) => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const titleId = useId();
  const [value, setValue] = useState("");
  const [query, setQuery] = useState("");
  const term = value.trim();
  useEffect(() => {
    const element = dialog.current;
    if (!element) return;
    const trigger = document.activeElement;
    element.showModal();
    input.current?.focus();
    return () => {
      if (element.open) element.close();
      if (trigger instanceof HTMLElement && trigger.isConnected)
        trigger.focus();
    };
  }, []);
  useEffect(() => {
    const timer = window.setTimeout(() => setQuery(term), 180);
    return () => window.clearTimeout(timer);
  }, [term]);
  const matching = useInfiniteQuery({
    queryKey: ["workspace-search", query],
    queryFn: ({ pageParam }) => api.searchWorkspace(query, pageParam),
    initialPageParam: 0,
    getNextPageParam: (last) => last.next_offset ?? undefined,
    enabled: connected && !!query && query === term,
  });
  const hits =
    query === term
      ? (matching.data?.pages.flatMap((page) => page.items) ?? [])
      : [];
  const total = matching.data?.pages[0]?.total ?? 0;
  return (
    <dialog
      ref={dialog}
      className="dialog workspace-search-dialog"
      aria-labelledby={titleId}
      onKeyDownCapture={(event) => {
        if (event.key !== "Escape" || event.nativeEvent.isComposing) return;
        event.preventDefault();
        event.stopPropagation();
        onClose();
      }}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
    >
      <div className="dialog-header">
        <h2 id={titleId}>搜索个人研究空间</h2>
        <button
          type="button"
          className="icon-button"
          aria-label="关闭搜索"
          onClick={onClose}
        >
          <X size={20} />
        </button>
      </div>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          if (hits[0]) onOpen(hits[0]);
        }}
      >
        <label className="search workspace-search-field">
          <Search size={17} aria-hidden="true" />
          <input
            ref={input}
            type="search"
            maxLength={200}
            aria-label="搜索项目与论文"
            placeholder="输入项目名称、说明或论文题名"
            value={value}
            onChange={(event) => setValue(event.target.value)}
          />
        </label>
      </form>
      {!connected ? (
        <p role="status">等待本地引擎连接。</p>
      ) : !term ? null : query !== term || matching.isPending ? (
        <p role="status">正在搜索…</p>
      ) : matching.isError && !hits.length ? (
        <div role="alert" className="error-text">
          {matching.error.message}
          <button
            type="button"
            className="text-button"
            onClick={() => void matching.refetch()}
          >
            重试搜索
          </button>
        </div>
      ) : hits.length ? (
        <>
          <p role="status" className="workspace-search-count">
            {total} 条结果
          </p>
          <ul className="workspace-search-results">
            {hits.map((hit) => (
              <li key={`${hit.kind}:${hit.id}`}>
                <button type="button" onClick={() => onOpen(hit)}>
                  {hit.kind === "paper" ? (
                    <BookOpen size={17} aria-hidden="true" />
                  ) : (
                    <FolderOpen size={17} aria-hidden="true" />
                  )}
                  <span>
                    <strong>{hit.title}</strong>
                    <small>
                      {hit.kind === "paper"
                        ? `论文 · ${hit.project.name}`
                        : "研究项目"}
                    </small>
                  </span>
                </button>
              </li>
            ))}
          </ul>
          {matching.isFetchNextPageError && (
            <p role="alert" className="error-text">
              {matching.error?.message}
            </p>
          )}
          {matching.hasNextPage && (
            <button
              type="button"
              className="button secondary"
              disabled={matching.isFetchingNextPage}
              onClick={() => void matching.fetchNextPage()}
            >
              {matching.isFetchingNextPage ? "正在加载…" : "加载更多结果"}
            </button>
          )}
        </>
      ) : (
        <p role="status">没有找到匹配的项目或论文。</p>
      )}
    </dialog>
  );
}

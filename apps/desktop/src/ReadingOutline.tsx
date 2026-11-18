import {
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  ChevronDown,
  ChevronRight,
  LocateFixed,
  PanelLeftClose,
  PanelLeftOpen,
} from "lucide-react";
import "./readingOutline.css";

export type OutlineEntry = {
  id: string;
  label: string;
  targetId: string;
  parentId?: string | null;
  level?: number;
  detail?: string;
};

type OutlineNode = {
  entry: OutlineEntry;
  children: OutlineNode[];
  index: number;
};

function outlineTree(entries: OutlineEntry[]) {
  const nodes = new Map<string, OutlineNode>();
  for (const [index, entry] of entries.entries()) {
    if (!nodes.has(entry.id))
      nodes.set(entry.id, { entry, children: [], index });
  }
  const parents = new Map<string, string | null>();
  const stack: { id: string; level: number }[] = [];
  for (const { entry } of nodes.values()) {
    const level = Number.isFinite(entry.level)
      ? Math.max(1, Math.floor(entry.level!))
      : 1;
    while (stack.length && stack[stack.length - 1].level >= level) stack.pop();
    // An explicit null or unresolved parent remains a root. Only older flat
    // payloads without a parent field infer ancestry from preceding levels.
    const parent =
      entry.parentId === undefined ? stack.at(-1)?.id : entry.parentId;
    parents.set(
      entry.id,
      parent && parent !== entry.id && nodes.has(parent) ? parent : null,
    );
    stack.push({ id: entry.id, level });
  }
  // Invalid input must never recurse forever or hide an entire cyclic group.
  for (const id of nodes.keys()) {
    const seen = new Set<string>();
    let current: string | null | undefined = id;
    while (current) {
      if (seen.has(current)) {
        parents.set(current, null);
        break;
      }
      seen.add(current);
      current = parents.get(current);
    }
  }
  const roots: OutlineNode[] = [];
  for (const node of nodes.values()) {
    const parent = parents.get(node.entry.id);
    if (parent) nodes.get(parent)!.children.push(node);
    else roots.push(node);
  }
  return { roots, parents };
}

function ancestorIds(parents: Map<string, string | null>, id: string) {
  const result: string[] = [];
  let parent = parents.get(id);
  while (parent) {
    result.push(parent);
    parent = parents.get(parent);
  }
  return result;
}

function narrowViewport() {
  return typeof window.matchMedia === "function"
    ? window.matchMedia("(max-width: 980px)").matches
    : false;
}

function focusEntry(entry: OutlineEntry) {
  const target = document.getElementById(entry.targetId);
  target?.scrollIntoView?.({ block: "start", behavior: "auto" });
  target?.focus({ preventScroll: true });
}

function readingViewport(root: HTMLElement) {
  let top = 0;
  let bottom = window.innerHeight;
  let scroller: HTMLElement | null = null;
  for (let parent = root.parentElement; parent; parent = parent.parentElement) {
    if (/(auto|scroll)/.test(getComputedStyle(parent).overflowY)) {
      const bounds = parent.getBoundingClientRect();
      top = Math.max(top, bounds.top);
      bottom = Math.min(bottom, bounds.bottom);
      if (!scroller && parent.scrollHeight > parent.clientHeight)
        scroller = parent;
    }
  }
  return {
    top,
    bottom,
    scroller,
    readingLine: top + Math.min(140, Math.max(32, (bottom - top) * 0.2)),
  };
}

type ReadingAnchor = {
  element: HTMLElement;
  range: Range | null;
  fraction: number;
  position: number;
  scroller: HTMLElement | null;
  innerScroller: HTMLElement | null;
  innerTop: number;
};

function scrollOffset(scroller: HTMLElement | null) {
  return scroller ? scroller.scrollTop : window.scrollY;
}

function anchorPosition(anchor: ReadingAnchor) {
  const bounds = anchor.element.getBoundingClientRect();
  return anchor.range
    ? anchor.range.getBoundingClientRect().top
    : bounds.top + bounds.height * anchor.fraction;
}

function captureReadingAnchor(root: HTMLElement): ReadingAnchor | null {
  const content = root.querySelector<HTMLElement>(".reading-outline-content");
  if (!content) return null;
  const { top, bottom, readingLine, scroller } = readingViewport(root);
  const marked = content.querySelectorAll<HTMLElement>("[data-reading-anchor]");
  const blocks = marked.length
    ? marked
    : content.querySelectorAll<HTMLElement>("h1,h2,h3,h4,h5,h6,p,pre");
  let candidate: {
    element: HTMLElement;
    bounds: DOMRect;
    distance: number;
  } | null = null;
  for (const element of blocks) {
    const bounds = element.getBoundingClientRect();
    if (bounds.height <= 0 || bounds.bottom <= top || bounds.top >= bottom)
      continue;
    const distance =
      bounds.top > readingLine
        ? bounds.top - readingLine
        : Math.max(0, readingLine - bounds.bottom);
    if (!candidate || distance < candidate.distance)
      candidate = { element, bounds, distance };
  }
  if (!candidate) return null;
  const { element, bounds } = candidate;
  const y = Math.max(bounds.top + 1, Math.min(readingLine, bounds.bottom - 1));
  // A text position survives line wrapping more precisely than the section's
  // heading or its absolute document offset. Other engines use the block fallback.
  const caret = (
    document as Document & {
      caretRangeFromPoint?: (x: number, y: number) => Range | null;
    }
  ).caretRangeFromPoint?.(bounds.left + Math.min(8, bounds.width / 2), y);
  const range =
    caret &&
    element.contains(caret.startContainer) &&
    caret.getBoundingClientRect().height > 0
      ? caret
      : null;
  let innerScroller: HTMLElement | null = null;
  if (range) {
    for (
      let parent: HTMLElement | null = element;
      parent && parent !== root;
      parent = parent.parentElement
    ) {
      if (
        /(auto|scroll)/.test(getComputedStyle(parent).overflowY) &&
        parent.scrollHeight > parent.clientHeight
      ) {
        innerScroller = parent;
        break;
      }
    }
  }
  return {
    element,
    range,
    fraction: (y - bounds.top) / bounds.height,
    position: range ? range.getBoundingClientRect().top : y,
    scroller,
    innerScroller,
    innerTop: innerScroller?.getBoundingClientRect().top ?? 0,
  };
}

function revealCurrent(
  navigation: HTMLElement | null,
  currentId: string,
  focus = false,
) {
  if (!navigation) return;
  const button = Array.from(
    navigation.querySelectorAll<HTMLButtonElement>("button[data-outline-id]"),
  ).find((item) => item.dataset.outlineId === currentId);
  if (!button || button.closest("[hidden]")) return;
  const bounds = navigation.getBoundingClientRect();
  const item = button.getBoundingClientRect();
  // Change only the directory scroll offset, never the article viewport.
  if (item.top < bounds.top) navigation.scrollTop -= bounds.top - item.top;
  else if (item.bottom > bounds.bottom)
    navigation.scrollTop += item.bottom - bounds.bottom;
  if (focus) button.focus({ preventScroll: true });
}

/** Local reading navigation: it never selects a model scope or starts a task. */
export function ReadingOutline({
  entries,
  activeId,
  onSelect,
  trackScroll = false,
  controls,
  children,
}: {
  entries: OutlineEntry[];
  activeId?: string;
  onSelect?: (id: string) => void;
  trackScroll?: boolean;
  controls?: ReactNode;
  children: ReactNode;
}) {
  const [expanded, setExpanded] = useState(() => !narrowViewport());
  const [narrow, setNarrow] = useState(narrowViewport);
  const narrowRef = useRef(narrow);
  const [observedId, setObservedId] = useState(entries[0]?.id ?? "");
  const [collapsed, setCollapsed] = useState<Set<string>>(() => new Set());
  const tree = useMemo(() => outlineTree(entries), [entries]);
  const previousCurrent = useRef<{ id: string; ancestors: string } | null>(
    null,
  );
  const layout = useRef<HTMLDivElement>(null);
  const sidebar = useRef<HTMLElement>(null);
  const list = useRef<HTMLElement>(null);
  const toggle = useRef<HTMLButtonElement>(null);
  const navigationFrame = useRef(0);
  const anchorFrame = useRef(0);
  const pendingAnchor = useRef<ReadingAnchor | null>(null);
  const stableAnchor = useRef<{
    anchor: ReadingAnchor;
    outerOffset: number;
    innerOffset: number;
    width: number;
  } | null>(null);
  const restoreNativeAnchor = useRef<(() => void) | null>(null);
  const panelId = useId();
  const currentId = activeId ?? observedId;
  const current = entries.find((entry) => entry.id === currentId);
  const entrySignature = entries.map((entry) => entry.targetId).join("\u0000");
  const currentAncestorIds = ancestorIds(tree.parents, currentId);
  const currentAncestorSignature = JSON.stringify(currentAncestorIds);
  const currentAncestors = new Set(currentAncestorIds);

  const openAncestors = useCallback(
    (id: string) => {
      const ancestors = ancestorIds(tree.parents, id);
      setCollapsed((previous) => {
        if (!ancestors.some((ancestor) => previous.has(ancestor)))
          return previous;
        const next = new Set(previous);
        ancestors.forEach((ancestor) => next.delete(ancestor));
        return next;
      });
    },
    [tree],
  );

  useEffect(() => {
    // Reveal a newly selected/read chapter, while respecting a reader who
    // deliberately folds the branch containing the unchanged current chapter.
    if (
      previousCurrent.current?.id === currentId &&
      previousCurrent.current.ancestors === currentAncestorSignature
    )
      return;
    previousCurrent.current = {
      id: currentId,
      ancestors: currentAncestorSignature,
    };
    openAncestors(currentId);
  }, [currentId, currentAncestorSignature, openAncestors]);

  useEffect(
    () => () => {
      cancelAnimationFrame(navigationFrame.current);
      cancelAnimationFrame(anchorFrame.current);
      restoreNativeAnchor.current?.();
    },
    [],
  );

  const setOutlineExpanded = useCallback(
    (next: boolean) => {
      if (next === expanded) return;
      cancelAnimationFrame(anchorFrame.current);
      restoreNativeAnchor.current?.();
      restoreNativeAnchor.current = null;
      if (!narrowRef.current && layout.current) {
        const previous = stableAnchor.current;
        // Reuse the same source character until the reader scrolls, instead of
        // choosing a different line start after every width change.
        const anchor =
          previous &&
          previous.anchor.element.isConnected &&
          previous.width === layout.current.getBoundingClientRect().width &&
          Math.abs(
            scrollOffset(previous.anchor.scroller) - previous.outerOffset,
          ) < 1 &&
          Math.abs(
            (previous.anchor.innerScroller?.scrollTop ?? 0) -
              previous.innerOffset,
          ) < 1 &&
          Math.abs(anchorPosition(previous.anchor) - previous.anchor.position) <
            1
            ? previous.anchor
            : captureReadingAnchor(layout.current);
        pendingAnchor.current = anchor;
        if (anchor) {
          const scrollRoots = [
            anchor.scroller ||
              (document.scrollingElement as HTMLElement | null),
            anchor.innerScroller,
          ].filter((element): element is HTMLElement => element !== null);
          const previousValues = scrollRoots.map(
            (element) => element.style.overflowAnchor,
          );
          scrollRoots.forEach((element) => {
            element.style.overflowAnchor = "none";
          });
          restoreNativeAnchor.current = () => {
            scrollRoots.forEach((element, index) => {
              element.style.overflowAnchor = previousValues[index];
            });
          };
        }
      }
      setExpanded(next);
    },
    [expanded],
  );

  useLayoutEffect(() => {
    const anchor = pendingAnchor.current;
    pendingAnchor.current = null;
    if (!anchor) return;
    if (anchor.element.isConnected) {
      const delta = anchor.innerScroller
        ? anchor.innerScroller.getBoundingClientRect().top - anchor.innerTop
        : anchorPosition(anchor) - anchor.position;
      if (anchor.scroller) anchor.scroller.scrollTop += delta;
      else window.scrollBy({ top: delta, behavior: "instant" });
      if (anchor.innerScroller)
        anchor.innerScroller.scrollTop +=
          anchorPosition(anchor) - anchor.position;
      stableAnchor.current = {
        anchor,
        outerOffset: scrollOffset(anchor.scroller),
        innerOffset: anchor.innerScroller?.scrollTop ?? 0,
        width: layout.current?.getBoundingClientRect().width ?? 0,
      };
    }
    anchorFrame.current = requestAnimationFrame(() => {
      restoreNativeAnchor.current?.();
      restoreNativeAnchor.current = null;
    });
  }, [expanded]);

  useEffect(() => {
    const root = layout.current;
    if (!root) return;
    const changed = () => {
      const width = root.getBoundingClientRect().width;
      const next = width > 0 ? width < 880 : narrowViewport();
      if (next === narrowRef.current) return;
      narrowRef.current = next;
      setNarrow(next);
      if (next) {
        if (sidebar.current?.contains(document.activeElement))
          toggle.current?.focus({ preventScroll: true });
        setExpanded(false);
      }
    };
    const resize =
      typeof ResizeObserver === "function" ? new ResizeObserver(changed) : null;
    resize?.observe(root);
    window.addEventListener("resize", changed);
    // Initial measurement runs after mounting into the actual app workspace.
    const frame = requestAnimationFrame(changed);
    return () => {
      cancelAnimationFrame(frame);
      resize?.disconnect();
      window.removeEventListener("resize", changed);
    };
  }, []);

  useEffect(() => {
    if (!expanded) return;
    const dismiss = () => {
      if (sidebar.current?.contains(document.activeElement))
        toggle.current?.focus({ preventScroll: true });
      setOutlineExpanded(false);
    };
    const outside = (event: PointerEvent) => {
      if (
        narrowRef.current &&
        event.target instanceof Node &&
        !sidebar.current?.contains(event.target)
      )
        dismiss();
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") dismiss();
    };
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", escape);
    };
  }, [expanded, setOutlineExpanded]);

  useEffect(() => {
    if (!trackScroll || !layout.current) return;
    const root = layout.current;
    const targets = entries
      .map((entry) => ({
        entry,
        element: document.getElementById(entry.targetId),
      }))
      .filter((item) => item.element !== null);
    if (!targets.length) return;
    let frame = 0;
    const readPosition = () => {
      frame = 0;
      const { top, bottom, scroller, readingLine } = readingViewport(root);
      let next = targets[0].entry.id;
      for (const { entry, element } of targets) {
        if (element!.getBoundingClientRect().top <= readingLine)
          next = entry.id;
        else break;
      }
      const atEnd = scroller
        ? scroller.scrollHeight > scroller.clientHeight + 2 &&
          scroller.scrollTop + scroller.clientHeight >=
            scroller.scrollHeight - 2
        : document.documentElement.scrollHeight > window.innerHeight + 2 &&
          window.scrollY + window.innerHeight >=
            document.documentElement.scrollHeight - 2;
      if (atEnd) {
        // A short final section may never reach the normal reading line.
        for (const { entry, element } of targets) {
          const bounds = element!.getBoundingClientRect();
          if (bounds.top < bottom && bounds.bottom > top) next = entry.id;
        }
      }
      setObservedId((previous) => (previous === next ? previous : next));
    };
    const schedule = (event?: Event) => {
      if (event?.target instanceof Node && list.current?.contains(event.target))
        return;
      if (!frame) frame = requestAnimationFrame(readPosition);
    };
    schedule();
    window.addEventListener("scroll", schedule, true);
    window.addEventListener("resize", schedule);
    const resize =
      typeof ResizeObserver === "function"
        ? new ResizeObserver(() => schedule())
        : null;
    resize?.observe(root);
    return () => {
      cancelAnimationFrame(frame);
      resize?.disconnect();
      window.removeEventListener("scroll", schedule, true);
      window.removeEventListener("resize", schedule);
    };
    // Target identities determine the observed document, not polling object identities.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [entrySignature, trackScroll]);

  useEffect(() => {
    if (!expanded || !currentId || !list.current) return;
    revealCurrent(list.current, currentId);
  }, [currentId, expanded, collapsed]);

  const choose = (entry: OutlineEntry) => {
    stableAnchor.current = null;
    setObservedId(entry.id);
    onSelect?.(entry.id);
    if (narrow) setExpanded(false);
    // Explicit navigation survives replacement of an old selected-paragraph
    // view by its parent. The globally unique section/unit target is looked
    // up after React commits; no state or detached element is retained.
    requestAnimationFrame(() => focusEntry(entry));
  };

  const renderNode = (node: OutlineNode, depth: number): ReactNode => {
    const { entry, children: descendants, index } = node;
    const hasChildren = descendants.length > 0;
    const branchExpanded = !collapsed.has(entry.id);
    const childrenId = `${panelId}-children-${index}`;
    return (
      <li key={entry.id} data-outline-level={depth}>
        <div
          className="reading-outline-row"
          data-current-branch={currentAncestors.has(entry.id)}
        >
          {hasChildren ? (
            <button
              type="button"
              className="reading-outline-branch"
              aria-label={`${branchExpanded ? "收起" : "展开"} ${entry.label} 的子章节`}
              aria-expanded={branchExpanded}
              aria-controls={childrenId}
              onClick={() =>
                setCollapsed((previous) => {
                  const next = new Set(previous);
                  if (next.has(entry.id)) next.delete(entry.id);
                  else next.add(entry.id);
                  return next;
                })
              }
            >
              {branchExpanded ? (
                <ChevronDown size={14} />
              ) : (
                <ChevronRight size={14} />
              )}
            </button>
          ) : (
            <span className="reading-outline-leaf-space" aria-hidden="true" />
          )}
          <button
            type="button"
            className="reading-outline-entry"
            data-outline-id={entry.id}
            aria-label={entry.label}
            aria-current={entry.id === currentId ? "location" : undefined}
            onClick={() => choose(entry)}
          >
            <span>{entry.label}</span>
            {entry.detail && <small>{entry.detail}</small>}
          </button>
        </div>
        {hasChildren && (
          <ul
            id={childrenId}
            className="reading-outline-children"
            data-indent={depth < 4}
            hidden={!branchExpanded}
          >
            {descendants.map((child) => renderNode(child, depth + 1))}
          </ul>
        )}
      </li>
    );
  };

  return (
    <div
      className="reading-outline-layout"
      data-expanded={expanded}
      data-narrow={narrow}
      ref={layout}
    >
      <aside
        ref={sidebar}
        className="reading-outline-sidebar"
        aria-label="阅读导航"
      >
        <div className="reading-outline-toolbar">
          <button
            ref={toggle}
            type="button"
            className="reading-outline-toggle"
            aria-expanded={expanded}
            aria-controls={panelId}
            aria-label={expanded ? "收起文章目录" : "展开文章目录"}
            title={expanded ? "收起文章目录" : "展开文章目录"}
            onClick={() => setOutlineExpanded(!expanded)}
          >
            {expanded ? (
              <PanelLeftClose size={18} />
            ) : (
              <PanelLeftOpen size={18} />
            )}
            <span>文章目录</span>
          </button>
          <button
            type="button"
            className="reading-outline-locate"
            aria-label="在目录中定位当前章节"
            title={
              current
                ? `在目录中定位当前章节：${current.label}`
                : "请先选择章节"
            }
            disabled={!current}
            onClick={() => {
              openAncestors(currentId);
              setOutlineExpanded(true);
              cancelAnimationFrame(navigationFrame.current);
              navigationFrame.current = requestAnimationFrame(() =>
                revealCurrent(list.current, currentId, true),
              );
            }}
          >
            <LocateFixed size={17} />
          </button>
        </div>
        <div id={panelId} className="reading-outline-panel" hidden={!expanded}>
          <p className="reading-outline-position">
            <span>当前阅读</span>
            <strong>{current?.label || "请选择章节"}</strong>
          </p>
          {controls && (
            <div className="reading-outline-controls">{controls}</div>
          )}
          <nav
            ref={list}
            aria-label="文章目录"
            className="reading-outline-list"
          >
            <ul className="reading-outline-tree">
              {tree.roots.map((node) => renderNode(node, 1))}
            </ul>
            {!entries.length && <p className="muted">尚无可定位的章节。</p>}
          </nav>
        </div>
      </aside>
      <div className="reading-outline-content">{children}</div>
    </div>
  );
}

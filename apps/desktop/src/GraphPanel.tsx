import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { Maximize2, Minimize2 } from "lucide-react";
import "./GraphPanel.css";

const focusableSelector = [
  "a[href]",
  "button",
  "input:not([type='hidden'])",
  "select",
  "textarea",
  "summary",
  "[tabindex]",
  "[contenteditable='true']",
].join(",");

function focusableElements(panel: HTMLElement): HTMLElement[] {
  return [...panel.querySelectorAll<HTMLElement>(focusableSelector)].filter(
    (element) => {
      if (
        element.tabIndex < 0 ||
        element.matches(":disabled") ||
        element.closest("[hidden], [inert], [aria-hidden='true']")
      )
        return false;
      // A closed evidence disclosure may contain controls that remain in the
      // DOM. They must not become a keyboard boundary while visually hidden.
      for (
        let ancestor: HTMLElement | null = element;
        ancestor;
        ancestor = ancestor.parentElement
      ) {
        const style = window.getComputedStyle(ancestor);
        if (style.display === "none" || style.visibility === "hidden")
          return false;
        if (ancestor instanceof HTMLDetailsElement && !ancestor.open) {
          const summary = ancestor.querySelector(":scope > summary");
          if (!summary?.contains(element)) return false;
        }
        if (ancestor === panel) break;
      }
      return true;
    },
  );
}

export function GraphPanel({
  children,
  toolbar,
  legend,
  title = "知识图谱",
}: {
  children: ReactNode;
  toolbar?: ReactNode;
  legend?: ReactNode;
  title?: string;
}) {
  const [fullscreen, setFullscreen] = useState(false);
  const panel = useRef<HTMLElement>(null);
  const toggle = useRef<HTMLButtonElement>(null);
  const titleId = useId();

  useEffect(() => {
    if (!fullscreen || !panel.current) return;
    const container = panel.current;
    const trigger = toggle.current;
    const body = document.body;
    const overflow = body.style.getPropertyValue("overflow");
    const priority = body.style.getPropertyPriority("overflow");
    body.style.setProperty("overflow", "hidden");
    trigger?.focus({ preventScroll: true });

    function containFocus(event: FocusEvent) {
      if (event.target instanceof Node && !container.contains(event.target)) {
        trigger?.focus({ preventScroll: true });
      }
    }

    function handleKey(event: KeyboardEvent) {
      if (event.defaultPrevented) return;
      if (event.key === "Escape") {
        event.preventDefault();
        setFullscreen(false);
        return;
      }
      if (event.key !== "Tab") return;
      const elements = focusableElements(container);
      const first = elements[0] ?? trigger;
      const last = elements.at(-1) ?? trigger;
      const active = document.activeElement;
      if (
        !container.contains(active) ||
        (event.shiftKey && active === first) ||
        (!event.shiftKey && active === last)
      ) {
        event.preventDefault();
        (event.shiftKey ? last : first)?.focus({ preventScroll: true });
      }
    }

    document.addEventListener("keydown", handleKey);
    document.addEventListener("focusin", containFocus);
    return () => {
      document.removeEventListener("keydown", handleKey);
      document.removeEventListener("focusin", containFocus);
      if (overflow) body.style.setProperty("overflow", overflow, priority);
      else body.style.removeProperty("overflow");
      if (trigger?.isConnected) trigger.focus({ preventScroll: true });
    };
  }, [fullscreen]);

  return (
    <section
      ref={panel}
      className={`graph-panel${fullscreen ? " graph-panel--fullscreen" : ""}`}
      role={fullscreen ? "dialog" : "region"}
      aria-modal={fullscreen || undefined}
      aria-labelledby={titleId}
    >
      <header className="graph-panel__header">
        <h3 id={titleId}>{title}</h3>
        <div className="graph-panel__actions">
          {toolbar && <div className="graph-panel__toolbar">{toolbar}</div>}
          <button
            ref={toggle}
            type="button"
            className="graph-panel__toggle"
            onClick={() => setFullscreen((value) => !value)}
            aria-pressed={fullscreen}
            title={fullscreen ? "退出全屏（Esc）" : "全屏显示图谱"}
          >
            {fullscreen ? (
              <Minimize2 size={16} aria-hidden="true" />
            ) : (
              <Maximize2 size={16} aria-hidden="true" />
            )}
            <span>{fullscreen ? "退出全屏" : "全屏显示图谱"}</span>
          </button>
        </div>
      </header>
      {legend && <div className="graph-panel__legend">{legend}</div>}
      <div className="graph-panel__content">{children}</div>
    </section>
  );
}

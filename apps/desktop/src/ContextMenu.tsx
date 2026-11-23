import {
  useCallback,
  useLayoutEffect,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type MouseEvent as ReactMouseEvent,
} from "react";
import { createPortal } from "react-dom";
import "./contextMenu.css";

export type ContextMenuEvent =
  | MouseEvent
  | KeyboardEvent
  | ReactMouseEvent<Element>
  | ReactKeyboardEvent<Element>;

export type ContextMenuAction = {
  label: string;
  action: () => void;
  disabled?: boolean;
  danger?: boolean;
};

type Menu = {
  anchor: Element;
  host: Element;
  label: string;
  actions: ContextMenuAction[];
  x: number;
  y: number;
};

export function isContextMenuKey(event: { key: string; shiftKey: boolean }) {
  return event.key === "ContextMenu" || (event.shiftKey && event.key === "F10");
}

function ContextMenu({
  menu,
  onDismiss,
}: {
  menu: Menu;
  onDismiss: (anchor?: Element) => void;
}) {
  const menuRef = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const element = menuRef.current;
    if (!element) return;
    const bounds = element.getBoundingClientRect();
    const margin = 8;
    element.style.left = `${Math.max(margin, Math.min(menu.x, window.innerWidth - bounds.width - margin))}px`;
    element.style.top = `${Math.max(margin, Math.min(menu.y, window.innerHeight - bounds.height - margin))}px`;
    (
      element.querySelector<HTMLButtonElement>("button:not(:disabled)") ??
      element
    ).focus({
      preventScroll: true,
    });

    function dismissOutside(event: Event) {
      if (event.target instanceof Node && !element?.contains(event.target)) {
        onDismiss();
      }
    }

    function dismiss() {
      onDismiss();
    }

    document.addEventListener("pointerdown", dismissOutside, true);
    document.addEventListener("focusin", dismissOutside);
    document.addEventListener("scroll", dismissOutside, true);
    document.addEventListener("fullscreenchange", dismiss);
    window.addEventListener("resize", dismiss);
    window.addEventListener("blur", dismiss);
    return () => {
      document.removeEventListener("pointerdown", dismissOutside, true);
      document.removeEventListener("focusin", dismissOutside);
      document.removeEventListener("scroll", dismissOutside, true);
      document.removeEventListener("fullscreenchange", dismiss);
      window.removeEventListener("resize", dismiss);
      window.removeEventListener("blur", dismiss);
    };
  }, [menu, onDismiss]);

  function navigate(event: ReactKeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      onDismiss(menu.anchor);
      return;
    }
    if (event.key === "Tab") {
      onDismiss(menu.anchor);
      return;
    }
    if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    event.stopPropagation();
    const enabled = Array.from(
      event.currentTarget.querySelectorAll<HTMLButtonElement>(
        "button:not(:disabled)",
      ),
    );
    if (!enabled.length) return;
    const current = enabled.findIndex(
      (item) => item === document.activeElement,
    );
    const last = enabled.length - 1;
    const next =
      event.key === "Home"
        ? 0
        : event.key === "End" || (event.key === "ArrowUp" && current <= 0)
          ? last
          : event.key === "ArrowUp"
            ? current - 1
            : (current + 1) % enabled.length;
    enabled[next]?.focus();
  }

  return createPortal(
    <div
      ref={menuRef}
      className="app-context-menu"
      role="menu"
      aria-label={menu.label}
      tabIndex={-1}
      onKeyDown={navigate}
      onContextMenu={(event) => {
        event.preventDefault();
        event.stopPropagation();
      }}
    >
      {menu.actions.map((item) => (
        <button
          key={item.label}
          type="button"
          role="menuitem"
          tabIndex={-1}
          disabled={item.disabled}
          className={item.danger ? "app-context-menu-danger" : undefined}
          onClick={() => {
            onDismiss(menu.anchor);
            item.action();
          }}
        >
          {item.label}
        </button>
      ))}
    </div>,
    menu.host,
  );
}

export function useContextMenu() {
  const [menu, setMenu] = useState<Menu | null>(null);
  const dismiss = useCallback((anchor?: Element) => {
    setMenu(null);
    if (
      anchor?.isConnected &&
      (anchor instanceof HTMLElement || anchor instanceof SVGElement)
    ) {
      anchor.focus({ preventScroll: true });
    }
  }, []);

  function openContextMenu(
    event: ContextMenuEvent,
    label: string,
    actions: ContextMenuAction[],
  ) {
    const target = event.target;
    if (!(target instanceof Element) || !actions.length) return;
    if (
      target.closest(
        "input, textarea, select, [contenteditable]:not([contenteditable='false'])",
      )
    )
      return;
    const selection = document.getSelection();
    if (
      selection &&
      !selection.isCollapsed &&
      selection.containsNode(target, true)
    )
      return;
    event.preventDefault();
    event.stopPropagation();
    const keyboard = "key" in event;
    const anchor =
      keyboard || !(event.currentTarget instanceof Element)
        ? target
        : event.currentTarget;
    const positionedAtAnchor =
      keyboard || (event.clientX === 0 && event.clientY === 0);
    const bounds = positionedAtAnchor ? anchor.getBoundingClientRect() : null;
    setMenu({
      anchor,
      host:
        anchor.closest("dialog[open], [data-fullscreen]") ??
        document.fullscreenElement ??
        document.body,
      label,
      actions,
      x: bounds ? bounds.left : keyboard ? 0 : event.clientX,
      y: bounds ? bounds.bottom : keyboard ? 0 : event.clientY,
    });
  }

  function contextMenuProps(label: string, actions: ContextMenuAction[]) {
    return {
      "aria-haspopup": "menu" as const,
      onContextMenu: (event: ReactMouseEvent<Element>) =>
        openContextMenu(event, label, actions),
      onKeyDown: (event: ReactKeyboardEvent<Element>) => {
        if (isContextMenuKey(event)) openContextMenu(event, label, actions);
      },
    };
  }

  return {
    openContextMenu,
    contextMenuProps,
    contextMenu: menu ? <ContextMenu menu={menu} onDismiss={dismiss} /> : null,
  };
}

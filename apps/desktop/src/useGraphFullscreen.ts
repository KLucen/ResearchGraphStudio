import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { isTauri } from "@tauri-apps/api/core";
import { getCurrentWindow } from "@tauri-apps/api/window";
import "./graphFullscreen.css";

type FullscreenMode = "element" | "window" | "viewport";

export function useGraphFullscreen() {
  const containerRef = useRef<HTMLDivElement>(null);
  const toggleRef = useRef<HTMLButtonElement>(null);
  const restoreWindow = useRef<(() => Promise<void>) | null>(null);
  const changing = useRef(false);
  const [mode, setMode] = useState<FullscreenMode | null>(null);

  useEffect(() => {
    const element = containerRef.current;
    const handleFullscreenChange = () => {
      if (element && document.fullscreenElement === element) setMode("element");
      else setMode((current) => (current === "element" ? null : current));
    };
    document.addEventListener("fullscreenchange", handleFullscreenChange);
    return () => {
      document.removeEventListener("fullscreenchange", handleFullscreenChange);
      if (element && document.fullscreenElement === element) {
        void document.exitFullscreen().catch(() => {});
      }
      const restore = restoreWindow.current;
      restoreWindow.current = null;
      if (restore) void restore().catch(() => {});
    };
  }, []);

  useLayoutEffect(() => {
    if (!mode || !containerRef.current) return;
    const inert: Element[] = [];
    // Keep the existing map mounted and isolate focus from the rest of the app.
    for (
      let element: HTMLElement | null = containerRef.current;
      element?.parentElement && element !== document.body;
      element = element.parentElement
    ) {
      for (const sibling of element.parentElement.children) {
        if (sibling !== element && !sibling.hasAttribute("inert")) {
          sibling.setAttribute("inert", "");
          inert.push(sibling);
        }
      }
    }
    const control = toggleRef.current;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    control?.focus({ preventScroll: true });
    return () => {
      for (const sibling of inert) sibling.removeAttribute("inert");
      document.body.style.overflow = overflow;
      if (control?.isConnected) control.focus({ preventScroll: true });
    };
  }, [mode]);

  async function toggle() {
    const element = containerRef.current;
    if (!element || changing.current) return;
    changing.current = true;
    try {
      if (mode || document.fullscreenElement === element) {
        if (document.fullscreenElement === element)
          await document.exitFullscreen();
        if (restoreWindow.current) {
          await restoreWindow.current();
          restoreWindow.current = null;
        }
        setMode(null);
        return;
      }

      try {
        if (isTauri()) {
          const host = getCurrentWindow();
          if (!(await host.isFullscreen())) {
            await host.setFullscreen(true);
            if (containerRef.current !== element) {
              await host.setFullscreen(false);
              return;
            }
            restoreWindow.current = () => host.setFullscreen(false);
          }
          if (containerRef.current === element) setMode("window");
          return;
        }
        if (document.fullscreenEnabled && element.requestFullscreen) {
          await element.requestFullscreen();
          if (document.fullscreenElement === element) {
            setMode("element");
            return;
          }
        }
      } catch {
        // A restricted embedding can still expand the map to the viewport.
      }
      if (containerRef.current === element) setMode("viewport");
    } catch {
      // Keep the exit control visible if the fullscreen host is unavailable.
    } finally {
      changing.current = false;
    }
  }

  useEffect(() => {
    if (!mode) return;
    const onEscape = (event: KeyboardEvent) => {
      if (
        event.key !== "Escape" ||
        event.defaultPrevented ||
        (event.target instanceof Element &&
          event.target.closest("dialog[open]"))
      ) {
        return;
      }
      event.preventDefault();
      void toggle();
    };
    document.addEventListener("keydown", onEscape);
    return () => document.removeEventListener("keydown", onEscape);
  });

  return { containerRef, toggleRef, mode, toggle };
}

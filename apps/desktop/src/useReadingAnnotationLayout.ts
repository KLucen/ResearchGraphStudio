import { useLayoutEffect, useRef } from "react";

// Keep the paragraph analysis beside the beginning of its source. Highlight
// references are compact controls inside that analysis, not extra quote cards.
export function useReadingAnnotationLayout(contentKey: string) {
  const rowRef = useRef<HTMLElement>(null);
  useLayoutEffect(() => {
    const row = rowRef.current;
    if (!row) return;
    let frame = 0;
    let disposed = false;
    const measure = () => {
      if (disposed) return;
      const anchored = row.clientWidth >= 560;
      row.dataset.noteLayout = anchored ? "anchored" : "stacked";
      const rail = row.querySelector<HTMLElement>(".paper-paragraph-note");
      const source = row.querySelector<HTMLElement>(".paper-paragraph-english");
      if (!rail || !source) return;
      const comment = rail.querySelector<HTMLElement>(
        ".paper-paragraph-comment",
      );
      if (comment) {
        const gap = anchored
          ? Math.max(
              0,
              source.getBoundingClientRect().top -
                rail.getBoundingClientRect().top,
            )
          : 0;
        comment.style.marginTop = `${gap}px`;
      }
    };
    const schedule = () => {
      if (disposed) return;
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(measure);
    };
    measure();
    const observer =
      typeof ResizeObserver === "undefined"
        ? null
        : new ResizeObserver(schedule);
    observer?.observe(row);
    const source = row.querySelector(".paper-paragraph-source");
    if (source) observer?.observe(source);
    const english = row.querySelector(".paper-paragraph-english");
    if (english) observer?.observe(english);
    const metadata = row.querySelector(".paper-paragraph-meta");
    if (metadata) observer?.observe(metadata);
    row
      .querySelectorAll(".paper-paragraph-comment")
      .forEach((card) => observer?.observe(card));
    window.addEventListener("resize", schedule);
    document.fonts?.addEventListener("loadingdone", schedule);
    void document.fonts?.ready.then(schedule);
    return () => {
      disposed = true;
      cancelAnimationFrame(frame);
      observer?.disconnect();
      window.removeEventListener("resize", schedule);
      document.fonts?.removeEventListener("loadingdone", schedule);
    };
  }, [contentKey]);
  return rowRef;
}

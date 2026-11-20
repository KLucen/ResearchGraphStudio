import type { ChapterProgress } from "./api";
import "./chapterProgress.css";

export const chapterProgressLabels: Record<ChapterProgress, string> = {
  NOT_STARTED: "未开始",
  READING: "阅读中",
  COMPLETED: "已读完",
};

export function ChapterProgressControls({
  title,
  progress,
  disabled,
  onChange,
}: {
  title: string;
  progress: ChapterProgress;
  disabled?: boolean;
  onChange: (progress: ChapterProgress) => void;
}) {
  return (
    <footer className="chapter-reading-footer" data-chapter-progress-footer>
      <div
        className="chapter-reading-progress"
        role="group"
        aria-label={`${title} 阅读状态`}
      >
        <span className="chapter-reading-footer-title">
          {title} · 章末阅读状态
        </span>
        {(Object.keys(chapterProgressLabels) as ChapterProgress[]).map(
          (value) => (
            <button
              type="button"
              key={value}
              className="text-button"
              aria-pressed={progress === value}
              disabled={disabled}
              onClick={() => onChange(value)}
            >
              {chapterProgressLabels[value]}
            </button>
          ),
        )}
      </div>
    </footer>
  );
}

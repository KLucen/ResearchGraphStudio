import type { PaperList } from "./api";

export const QUERY_PAGE_SIZE = 10;
export type QueryPapers = PaperList["items"];

export function matchesPapers(ids: string[] | undefined, filter: string[]) {
  return !filter.length || (ids ?? []).some((id) => filter.includes(id));
}

export function pageItems<T>(items: T[], page: number) {
  const pages = Math.max(1, Math.ceil(items.length / QUERY_PAGE_SIZE));
  const current = Math.max(1, Math.min(page, pages));
  return {
    current,
    items: items.slice(
      (current - 1) * QUERY_PAGE_SIZE,
      current * QUERY_PAGE_SIZE,
    ),
  };
}

export function PaperDisplayFilter({
  label,
  papers,
  value,
  onChange,
}: {
  label: string;
  papers: QueryPapers;
  value: string[];
  onChange: (ids: string[]) => void;
}) {
  return (
    <details className="query-display-filter">
      <summary>
        {label} · {value.length ? `已选 ${value.length} 篇` : "全部论文"}
      </summary>
      <p className="quiet-note">
        仅筛选本板块展示；跨论文内容命中任一所选论文即保留。
      </p>
      <button
        type="button"
        className="text-button"
        onClick={() => onChange([])}
      >
        {label}：显示全部论文
      </button>
      <div className="query-paper-options">
        {papers.map((paper) => (
          <label key={paper.id}>
            <input
              type="checkbox"
              aria-label={`${label} · ${paper.title}`}
              checked={value.includes(paper.id)}
              onChange={(event) =>
                onChange(
                  event.target.checked
                    ? [...value, paper.id]
                    : value.filter((id) => id !== paper.id),
                )
              }
            />
            {paper.title}
          </label>
        ))}
      </div>
    </details>
  );
}

export function QueryPagination({
  label,
  total,
  page,
  onChange,
  disabled = false,
}: {
  label: string;
  total: number;
  page: number;
  onChange: (page: number) => void;
  disabled?: boolean;
}) {
  const pages = Math.max(1, Math.ceil(total / QUERY_PAGE_SIZE));
  const current = Math.max(1, Math.min(page, pages));
  return (
    <nav className="query-pagination" aria-label={`${label}分页`}>
      <span>
        共 {total} 条 · 每页 {QUERY_PAGE_SIZE} 条 · 第 {current} / {pages} 页
      </span>
      <div>
        <button
          type="button"
          className="text-button"
          aria-label={`${label}上一页`}
          disabled={disabled || current <= 1}
          onClick={() => onChange(current - 1)}
        >
          上一页
        </button>
        <label>
          页码
          <select
            aria-label={`${label}页码`}
            value={current}
            disabled={disabled || total === 0}
            onChange={(event) => onChange(Number(event.target.value))}
          >
            {Array.from({ length: pages }, (_, index) => (
              <option value={index + 1} key={index}>
                {index + 1}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          className="text-button"
          aria-label={`${label}下一页`}
          disabled={disabled || current >= pages}
          onClick={() => onChange(current + 1)}
        >
          下一页
        </button>
      </div>
    </nav>
  );
}

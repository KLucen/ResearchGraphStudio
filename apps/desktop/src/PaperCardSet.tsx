import { useMemo, useState } from "react";
import { Bookmark, Check, EyeOff, Search } from "lucide-react";
import {
  paperCardCategories,
  type DetailedPaperCard,
  type PaperCardEvidence,
  type PaperCardKind,
  type PaperCardSet as PaperCardSetData,
} from "./paperCardSetTypes";
import "./paperCardSet.css";

type CardPreference = {
  read?: boolean;
  saved?: boolean;
  hidden?: boolean;
  note?: string;
};
type CardPreferences = Record<string, CardPreference>;
type ViewFilter = "all" | "unread" | "saved" | "hidden";

function storedPreferences(key: string, cardIds: Set<string>): CardPreferences {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(key) ?? "{}");
    if (!value || typeof value !== "object" || Array.isArray(value)) return {};
    return Object.fromEntries(
      Object.entries(value).flatMap(([id, item]) => {
        if (
          !cardIds.has(id) ||
          !item ||
          typeof item !== "object" ||
          Array.isArray(item)
        )
          return [];
        const data = item as Record<string, unknown>;
        return [
          [
            id,
            {
              read: data.read === true,
              saved: data.saved === true,
              hidden: data.hidden === true,
              note:
                typeof data.note === "string" ? data.note.slice(0, 4000) : "",
            },
          ],
        ];
      }),
    );
  } catch {
    return {};
  }
}

export function PaperCardSet({
  data,
  paperId,
  revisionId,
  resultId,
  initialCardId = "",
  onOpenSection,
}: {
  data: PaperCardSetData;
  paperId: string;
  revisionId: string;
  resultId: string;
  initialCardId?: string;
  onOpenSection?: (sectionId: string, paragraphId?: string) => void;
}) {
  const storageKey = `rgs.paper-card-preferences.v1:${paperId}:${data.source_kind}:${revisionId}:${resultId}`;
  const cardIds = useMemo(
    () => new Set(data.cards.map((card) => card.id)),
    [data.cards],
  );
  const [preferences, setPreferences] = useState(() =>
    storedPreferences(storageKey, cardIds),
  );
  const [category, setCategory] = useState<PaperCardKind | "all">("all");
  const [view, setView] = useState<ViewFilter>("all");
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState(() =>
    cardIds.has(initialCardId) ? initialCardId : (data.cards[0]?.id ?? ""),
  );
  const [storageError, setStorageError] = useState("");
  const update = (id: string, patch: CardPreference) => {
    const next = { ...preferences, [id]: { ...preferences[id], ...patch } };
    try {
      localStorage.setItem(storageKey, JSON.stringify(next));
      setPreferences(next);
      setStorageError("");
      return true;
    } catch {
      setStorageError(
        "本机偏好暂时无法保存；当前页面仍可使用，本次更改尚未保存。",
      );
      return false;
    }
  };
  const term = search.trim().toLocaleLowerCase();
  const matchingCards = data.cards.filter((card) => {
    const preference = preferences[card.id] ?? {};
    if (view === "hidden" ? !preference.hidden : preference.hidden)
      return false;
    if (view === "saved" && !preference.saved) return false;
    if (view === "unread" && preference.read) return false;
    return (
      !term ||
      [
        card.title_zh,
        card.title_en,
        card.body_zh,
        card.reading_guide_zh,
        ...card.evidence.flatMap((item) => [
          item.quote_en,
          item.translation_zh,
        ]),
      ]
        .join(" ")
        .toLocaleLowerCase()
        .includes(term)
    );
  });
  const counts = new Map<PaperCardKind, number>();
  for (const card of matchingCards) {
    counts.set(card.kind, (counts.get(card.kind) ?? 0) + 1);
  }
  const visibleCards =
    category === "all"
      ? matchingCards
      : matchingCards.filter((card) => card.kind === category);
  const selected =
    visibleCards.find((card) => card.id === selectedId) ?? visibleCards[0];
  const overviewCards = data.cards.filter((card) =>
    data.overview_card_ids.includes(card.id),
  );
  const selectCard = (id: string) => {
    setCategory("all");
    setView(preferences[id]?.hidden ? "hidden" : "all");
    setSearch("");
    setSelectedId(id);
  };
  return (
    <div className="paper-card-set">
      <section
        className="card-set-overview"
        aria-labelledby="article-overview-title"
      >
        <h4 id="article-overview-title">文章总览</h4>
        <p className="card-set-prose">{data.article_overview_zh}</p>
        {overviewCards.length > 0 && (
          <div className="card-set-overview-links" aria-label="总览依据卡片">
            <span>回查卡片</span>
            {overviewCards.map((card) => (
              <button
                key={card.id}
                className="text-button"
                onClick={() => selectCard(card.id)}
              >
                {card.title_zh}
              </button>
            ))}
          </div>
        )}
      </section>
      <section
        className="card-set-introduction"
        aria-labelledby="card-set-intro-title"
      >
        <div>
          <h4 id="card-set-intro-title">这篇文章的卡片集</h4>
          <p>{data.card_set_intro_zh}</p>
        </div>
        <span className="card-set-total">
          {data.cards.length}
          <small>张卡片</small>
        </span>
      </section>
      {(data.coverage_notes.length > 0 || data.source_warnings.length > 0) && (
        <details className="card-set-coverage">
          <summary>材料覆盖与待核查内容</summary>
          <ul>
            {[
              ...new Set([...data.coverage_notes, ...data.source_warnings]),
            ].map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
        </details>
      )}
      <p className="card-set-provenance">
        {data.source_kind === "model_parse"
          ? "依据已保存的模型解析材料；引文匹配不代表已核验原 PDF。"
          : "依据已保存的本地解析材料，位置由程序绑定。"}
        中文译文为辅助翻译；来源可回查不等于科学结论已经验证。
      </p>
      <div className="card-set-toolbar">
        <label className="card-set-search">
          <Search size={16} aria-hidden="true" />
          <input
            aria-label="搜索文章卡片"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="搜索卡片标题、内容或原文"
          />
        </label>
        <label className="card-set-view">
          <span>查看</span>
          <select
            aria-label="卡片查看范围"
            value={view}
            onChange={(event) => setView(event.target.value as ViewFilter)}
          >
            <option value="all">全部可见</option>
            <option value="unread">尚未读完</option>
            <option value="saved">我的收藏</option>
            <option value="hidden">已隐藏</option>
          </select>
        </label>
      </div>
      <nav className="card-set-categories" aria-label="卡片类别">
        <button
          type="button"
          className={category === "all" ? "active" : ""}
          aria-pressed={category === "all"}
          onClick={() => setCategory("all")}
        >
          全部类别<span>{matchingCards.length}</span>
        </button>
        {paperCardCategories.map(({ kind, label }) => (
          <button
            type="button"
            key={kind}
            className={category === kind ? "active" : ""}
            aria-pressed={category === kind}
            onClick={() => setCategory(kind)}
          >
            {label}
            <span>{counts.get(kind) ?? 0}</span>
          </button>
        ))}
      </nav>
      {storageError && (
        <p role="alert" className="error-text">
          {storageError}
        </p>
      )}
      <div className="card-set-workbench">
        <aside className="card-set-navigation">
          <div className="card-set-index" aria-label="卡片目录">
            <p>显示 {visibleCards.length} 张卡片</p>
            {visibleCards.map((card) => (
              <button
                key={card.id}
                aria-current={selected?.id === card.id ? "true" : undefined}
                onClick={() => setSelectedId(card.id)}
              >
                <strong title={card.title_zh}>{card.title_zh}</strong>
                <span>
                  {preferences[card.id]?.read ? "已读完" : "未读完"}
                  {preferences[card.id]?.saved ? " · 已收藏" : ""}
                  {preferences[card.id]?.hidden ? " · 已隐藏" : ""}
                </span>
              </button>
            ))}
          </div>
        </aside>
        <div className="card-set-content">
          {selected ? (
            <CardDetail
              key={selected.id}
              card={selected}
              preference={preferences[selected.id] ?? {}}
              sourceKind={data.source_kind}
              onUpdate={(patch) => update(selected.id, patch)}
              onOpenSection={onOpenSection}
            />
          ) : (
            <div className="card-set-empty" role="status">
              <h4>此范围没有卡片</h4>
              <p>
                {view === "hidden"
                  ? "尚无隐藏卡片，或没有符合当前筛选的内容。"
                  : "试试其他类别、清空搜索，或从“已隐藏”中恢复卡片。"}
              </p>
              <button
                className="text-button"
                onClick={() => {
                  setCategory("all");
                  setSearch("");
                  setView("all");
                }}
              >
                重置筛选
              </button>
            </div>
          )}
        </div>
      </div>
      <p className="card-set-personal-note">
        已读、收藏、隐藏和个人笔记仅保存在本机当前卡片版本，不修改 AI
        内容，不发送模型请求。隐藏不等于删除。
      </p>
    </div>
  );
}

function CardDetail({
  card,
  preference,
  sourceKind,
  onUpdate,
  onOpenSection,
}: {
  card: DetailedPaperCard;
  preference: CardPreference;
  sourceKind: PaperCardSetData["source_kind"];
  onUpdate: (patch: CardPreference) => boolean;
  onOpenSection?: (sectionId: string, paragraphId?: string) => void;
}) {
  const [note, setNote] = useState(preference.note ?? "");
  const [noteSaved, setNoteSaved] = useState(false);
  const category = paperCardCategories.find(({ kind }) => kind === card.kind);
  return (
    <article
      className="detailed-paper-card"
      aria-label={`${category?.label ?? "知识"}卡片：${card.title_zh}`}
    >
      <header className="detailed-card-header">
        <div className="detailed-card-labels">
          <span>{category?.en ?? card.kind}</span>
          <span
            className={`card-attribution ${card.attribution.toLowerCase()}`}
          >
            {card.attribution === "AUTHOR"
              ? "作者陈述的概括"
              : "模型分析 · 待核查"}
          </span>
        </div>
        <h4>{card.title_zh}</h4>
        {card.title_en && (
          <p className="detailed-card-english-title">{card.title_en}</p>
        )}
        <p className="card-set-prose">{card.body_zh}</p>
      </header>
      {card.reading_guide_zh && (
        <div className="detailed-card-guide">
          <strong>阅读导引</strong>
          <p>{card.reading_guide_zh}</p>
        </div>
      )}
      <section className="detailed-card-evidence" aria-label="卡片原文依据">
        <h5>Paper Evidence / 原文依据</h5>
        {card.evidence.map((evidence, index) => (
          <Evidence
            key={`${evidence.source_id}:${evidence.occurrence_index}:${index}`}
            evidence={evidence}
            index={index}
            sourceKind={sourceKind}
            onOpenSection={onOpenSection}
          />
        ))}
      </section>
      <div className="detailed-card-actions" aria-label="卡片管理">
        <button
          className={preference.read ? "selected" : ""}
          aria-pressed={!!preference.read}
          onClick={() => onUpdate({ read: !preference.read })}
        >
          <Check size={15} aria-hidden="true" />
          {preference.read ? "已读完" : "标为已读完"}
        </button>
        <button
          className={preference.saved ? "selected" : ""}
          aria-pressed={!!preference.saved}
          onClick={() => onUpdate({ saved: !preference.saved })}
        >
          <Bookmark size={15} aria-hidden="true" />
          {preference.saved ? "取消收藏" : "收藏卡片"}
        </button>
        <button onClick={() => onUpdate({ hidden: !preference.hidden })}>
          <EyeOff size={15} aria-hidden="true" />
          {preference.hidden ? "恢复显示" : "隐藏卡片"}
        </button>
      </div>
      <details className="detailed-card-note" open={!!preference.note}>
        <summary>我的笔记{preference.note ? " · 已保存" : ""}</summary>
        <label>
          个人阅读笔记
          <textarea
            maxLength={4000}
            value={note}
            onChange={(event) => {
              setNote(event.target.value);
              setNoteSaved(false);
            }}
            placeholder="记录自己的理解、疑问或后续核查，不会覆盖作者陈述与 AI 分析。"
          />
        </label>
        <button
          className="button secondary"
          disabled={note === (preference.note ?? "")}
          onClick={() => {
            setNoteSaved(onUpdate({ note }));
          }}
        >
          保存个人笔记
        </button>
        {noteSaved && (
          <p role="status">个人笔记已在本机保存，本次模型调用为 0。</p>
        )}
      </details>
    </article>
  );
}

function Evidence({
  evidence,
  index,
  sourceKind,
  onOpenSection,
}: {
  evidence: PaperCardEvidence;
  index: number;
  sourceKind: PaperCardSetData["source_kind"];
  onOpenSection?: (sectionId: string, paragraphId?: string) => void;
}) {
  const position = evidence.position;
  const page = position.page_start;
  const pageLabel = page
    ? `第 ${page}${position.page_end && position.page_end !== page ? `–${position.page_end}` : ""} 页`
    : "页码不可用";
  const local = sourceKind === "local_revision";
  const firstOffset = position.local_offsets[0];
  return (
    <div className="card-evidence-item">
      <span className="card-evidence-number">依据 {index + 1}</span>
      <blockquote>
        <span className="card-evidence-language">原文 · 保留原语言</span>
        <p>{evidence.quote_en}</p>
      </blockquote>
      <div className="card-evidence-translation">
        <span className="card-evidence-language">译文（ZH）· 辅助翻译</span>
        <p>{evidence.translation_zh || "此条依据尚未提供中文译文。"}</p>
      </div>
      <div className="card-evidence-location">
        <span>Location</span>
        <strong>{position.chapter_title || "章节名称不可用"}</strong>
        <span>
          {pageLabel}
          {!local && position.segment_id ? " · 模型解析片段" : ""}
        </span>
        {local && position.chapter_ref && onOpenSection && (
          <button
            className="text-button"
            onClick={() =>
              onOpenSection(
                position.chapter_ref!,
                position.unit_id ?? firstOffset?.chunk_id,
              )
            }
          >
            查看对应原文
          </button>
        )}
      </div>
      <details className="card-evidence-anchor">
        <summary>定位信息</summary>
        <dl>
          <dt>来源</dt>
          <dd>{evidence.source_id}</dd>
          <dt>片段范围</dt>
          <dd>
            {position.source_offset_start}–{position.source_offset_end} 字符
          </dd>
          {position.segment_id && (
            <>
              <dt>解析片段</dt>
              <dd>{position.segment_id}</dd>
            </>
          )}
          {firstOffset && (
            <>
              <dt>本地文字块</dt>
              <dd>{firstOffset.chunk_id}</dd>
            </>
          )}
        </dl>
      </details>
    </div>
  );
}

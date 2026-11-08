"""Deterministic Wiki versions use the existing document Store and root evidence validator."""

import difflib
import html
import re
from typing import Any, Literal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from researchgraph.knowledge_models import ZoteroLink
from researchgraph.knowledge_store import KnowledgeError, KnowledgeStore, digest, text_hash
from researchgraph.models import Chunk, Paper, Project, now
from researchgraph.query_contracts import DocumentPassageInput, DocumentSaveRequest
from researchgraph.query_documents import validate_dependencies
from researchgraph.query_models import (
    QueryDocument,
    QueryDocumentVersion,
    QueryOperation,
    QueryPassage,
)
from researchgraph.wiki_contracts import WikiDraftInput, WikiPatchInput, WikiSaveCommand
from researchgraph.wiki_models import WikiPage, WikiSection, WikiVersion


def escaped(value: str) -> str:
    """Untrusted content is text, never HTML, images, executable URLs or Markdown links."""
    value = html.escape(value, quote=False).replace("\r\n", "\n").replace("\r", "\n")
    value = re.sub(r"([\\`*_{}\[\]()#!|>~])", r"\\\1", value)
    return value.replace(":", "&#58;")


def page_filename(page_id: str) -> str:
    # Formal IDs come from the Store. Validate rather than interpolate arbitrary strings.
    if not re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", page_id):
        raise KnowledgeError("WIKI_PAGE_ID_INVALID", "页面标识无效")
    return f"page-{page_id}.md"


def wiki_passage_state(session: Session, passage_id: str) -> dict[str, Any] | None:
    passage = session.get(QueryPassage, passage_id)
    section = session.get(WikiSection, passage_id)
    if (
        passage
        and session.get(WikiVersion, passage.version_id)
        and (
            not section
            or section.version_id != passage.version_id
            or text_hash(passage.text) != passage.sha256
        )
    ):
        return {"content_state": "invalid", "issues": ["WIKI_SNAPSHOT_INVALID"]}
    if section and section.stale_reason:
        return {"content_state": "stale", "issues": ["WIKI_SECTION_MARKED_STALE"]}
    return None


def _scope(session: Session, project_id: str, page_id: str) -> tuple[QueryDocument, WikiPage]:
    document = session.get(QueryDocument, page_id)
    page = session.get(WikiPage, page_id)
    if not page or not document or document.project_id != project_id or document.kind != "wiki":
        raise KnowledgeError("WIKI_NOT_FOUND", "当前项目中没有该受管页面")
    return document, page


def _sections(session: Session, version_id: str) -> list[dict[str, Any]]:
    entries = session.execute(
        select(QueryPassage, WikiSection)
        .join(WikiSection, WikiSection.passage_id == QueryPassage.id)
        .where(QueryPassage.version_id == version_id)
        .order_by(QueryPassage.ordinal)
    )
    return [
        {
            "section_id": s.section_id,
            "passage_id": p.id,
            "heading": s.heading,
            "text": p.text,
            "attribution": p.attribution,
            "dependencies": p.dependencies,
            "caveats": p.caveats,
            "conditions": s.conditions,
            "links": s.links,
            "stale_reason": s.stale_reason,
        }
        for p, s in entries
    ]


def _semantic(title: str, sections: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "title": title,
        "sections": [{k: v for k, v in s.items() if k != "passage_id"} for s in sections],
    }


def wiki_version_state(session: Session, version_id: str) -> dict[str, Any] | None:
    """Check one complete immutable snapshot, including missing or mismatched sidecars.

    Call once per document, not once per passage: the page hash covers the ordered sections.
    Source validity remains a separate per-passage check so one stale source does not hide
    unrelated valid paragraphs.
    """
    wiki = session.get(WikiVersion, version_id)
    if not wiki:
        return None
    passages = list(
        session.scalars(select(QueryPassage).where(QueryPassage.version_id == version_id))
    )
    sidecars = {
        section.passage_id: section
        for section in session.scalars(
            select(WikiSection).where(WikiSection.passage_id.in_([p.id for p in passages]))
        )
    }
    sections = _sections(session, version_id)
    if (
        not passages
        or len(passages) != len(sections)
        or any(
            p.id not in sidecars
            or sidecars[p.id].version_id != p.version_id
            or text_hash(p.text) != p.sha256
            for p in passages
        )
        or digest(_semantic(wiki.title, sections)) != wiki.content_hash
    ):
        return {"content_state": "invalid", "issues": ["WIKI_SNAPSHOT_INVALID"]}
    return None


def _reference(session: Session, root: dict[str, Any]) -> dict[str, Any]:
    record = dict(root)
    record["ref"] = "r" + digest(root)[:20]
    if root["source_kind"] == "paper":
        paper = session.get(Paper, root["paper_id"])
        record["title"] = paper.title if paper else "来源论文"
        chunk_id = root.get("chunk_id") or (root["id"] if root.get("type") == "chunk" else None)
        chunk = session.get(Chunk, chunk_id) if chunk_id else None
        if chunk:
            record["page_index"], record["page_label"] = chunk.page_index, chunk.page_label
        link = session.scalar(
            select(ZoteroLink)
            .where(
                ZoteroLink.paper_id == root["paper_id"],
                ZoteroLink.document_version_id == root["document_version_id"],
            )
            .order_by(ZoteroLink.id)
        )
        if link and re.fullmatch(r"[A-Z0-9]{8}", link.attachment_key):
            library = re.fullmatch(r"(users|groups)/([0-9]{1,16})", link.library_id)
            if library:
                base = "library" if library[1] == "users" else f"groups/{library[2]}"
                record["zotero_url"] = f"zotero://open-pdf/{base}/items/{link.attachment_key}"
                if chunk:
                    record["zotero_url"] += f"?page={chunk.page_index + 1}"
    elif root["source_kind"] == "annotation":
        from researchgraph.knowledge_models import Annotation

        # A user's comment remains a personal source even when its highlight has a valid anchor.
        record["attribution"] = "user_view"
        record["source_verified"] = False
        annotation = session.get(Annotation, root["id"])
        if annotation and root.get("field") == "comment":
            record["text"] = annotation.comment
        library = re.fullmatch(r"(users|groups)/([0-9]{1,16})", str(root.get("library_id", "")))
        attachment = str(root.get("attachment_key", ""))
        if library and re.fullmatch(r"[A-Z0-9]{8}", attachment):
            base = "library" if library[1] == "users" else f"groups/{library[2]}"
            record["zotero_url"] = f"zotero://open-pdf/{base}/items/{attachment}"
            page = root.get("page_index")
            if root.get("anchor_status") == "block_matched" and type(page) is int and page >= 0:
                record["zotero_url"] += f"?page={page + 1}"
            else:
                record.pop("page_index", None)
        else:
            record.pop("page_index", None)
    elif root["source_kind"] == "external":
        from researchgraph.external_document_models import ExternalDocumentVersion

        origin = session.get(ExternalDocumentVersion, root["id"])
        if origin:
            record["title"] = origin.title
            record["attribution"] = origin.attribution
        record["source_verified"] = False
    return record


def render_markdown(
    page_id: str,
    title: str,
    sections: list[dict[str, Any]],
    references: list[dict[str, Any]],
    section_refs: dict[str, list[str]],
    content_hash: str,
) -> str:
    """No timestamps, random render IDs, path guesses or model-controlled markup."""
    lines = [
        "---",
        "researchgraph: wiki-1",
        f"page_id: {page_id}",
        f"content_hash: {content_hash}",
        "---",
        "",
        "# " + escaped(title),
        "",
    ]
    for section in sections:
        sid = section["section_id"]
        lines.extend([f'<a id="section-{sid}"></a>', ""])
        if section["heading"]:
            lines.extend(["## " + escaped(section["heading"]), ""])
        lines.extend([escaped(section["text"]), ""])
        lines.extend(["归属：" + escaped(section["attribution"]), ""])
        if section.get("stale_reason"):
            lines.extend(["依据状态：过期 — " + escaped(section["stale_reason"]), ""])
        refs = section_refs.get(sid, [])
        if refs:
            lines.extend(["依据：" + " · ".join(f"[{r}](#ref-{r})" for r in refs), ""])
        if section["conditions"]:
            lines.extend(["| 条件 | 状态 | 值 | 单位 |", "| --- | --- | --- | --- |"])
            for condition in section["conditions"]:
                lines.append(
                    "| "
                    + " | ".join(
                        escaped(str(condition.get(key) or "—")).replace("\n", " ")
                        for key in ("dimension", "state", "value", "unit")
                    )
                    + " |"
                )
            lines.append("")
        for caveat in section["caveats"]:
            lines.extend(["限制：" + escaped(caveat), ""])
        for linked in section["links"]:
            lines.extend([f"[相关页面]({page_filename(linked)})", ""])
    lines.extend(["## 原文依据", ""])
    for ref in references:
        lines.extend([f'<a id="ref-{ref["ref"]}"></a>', ""])
        if ref["source_kind"] == "paper":
            lines.extend([escaped(ref["title"]), ""])
            lines.extend(
                [
                    "文献版本：" + escaped(ref["document_version_id"]),
                    "",
                    "证据：" + escaped(ref["id"]),
                    "",
                ]
            )
            if "page_index" in ref:
                lines.extend(["PDF 页：" + str(ref["page_index"] + 1), ""])
            if "start" in ref and "end" in ref:
                lines.extend([f"文本跨度：{ref['start']}–{ref['end']}", ""])
            if ref.get("quote"):
                lines.extend(["> " + escaped(ref["quote"]).replace("\n", "\n> "), ""])
            if ref.get("zotero_url"):
                lines.extend([f"[在 Zotero 中打开]({ref['zotero_url']})", ""])
        elif ref["source_kind"] == "annotation":
            lines.extend(
                [
                    "批注评论（用户）：" + escaped(str(ref["id"])),
                    "",
                    "归属：用户观点；不作为论文科学证据",
                    "",
                    "批注标识：" + escaped(str(ref.get("annotation_key", ""))),
                    "",
                ]
            )
            if ref.get("text"):
                lines.extend(["> " + escaped(str(ref["text"])).replace("\n", "\n> "), ""])
            page = ref.get("page_index")
            if ref.get("anchor_status") == "block_matched" and type(page) is int and page >= 0:
                lines.extend(["PDF 页：" + str(page + 1), ""])
            if ref.get("zotero_url"):
                lines.extend([f"[在 Zotero 中打开]({ref['zotero_url']})", ""])
        elif ref["source_kind"] == "external":
            label = (
                "个人资料（用户观点）"
                if ref.get("attribution") == "user_view"
                else "外部资料（作者归属未验证）"
            )
            lines.extend(
                [
                    label + "：" + escaped(str(ref.get("title", ref["id"]))),
                    "",
                    "独立文档版本：" + escaped(str(ref.get("version_id", ref["id"]))),
                    "",
                    "相对路径：" + escaped(str(ref.get("relative_path", ""))),
                    "",
                    "来源状态：未由论文证据核验",
                    "",
                ]
            )
        else:
            lines.extend(["个人/外部资料：" + escaped(str(ref.get("id", ""))), ""])
    return "\n".join(lines).rstrip() + "\n"


def _derive_references(
    session: Session, project_id: str, sections: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    references: dict[str, dict[str, Any]] = {}
    section_refs: dict[str, list[str]] = {}
    for section in sections:
        checked = validate_dependencies(session, project_id, section["dependencies"], True, "local")
        refs = []
        for root in checked["roots"]:
            reference = _reference(session, root)
            references[reference["ref"]] = reference
            refs.append(reference["ref"])
        section_refs[section["section_id"]] = sorted(set(refs))
    return [references[k] for k in sorted(references)], section_refs


def read_page(
    session: Session,
    project_id: str,
    page_id: str,
    version_id: str | None = None,
    *,
    include_personal: bool = False,
    purpose: str = "local",
    require_local: bool = False,
) -> dict[str, Any]:
    document, page = _scope(session, project_id, page_id)
    version_id = version_id or page.head_version_id
    version = session.get(QueryDocumentVersion, version_id)
    wiki = session.get(WikiVersion, version_id)
    if not version or not wiki or version.document_id != page_id:
        raise KnowledgeError("WIKI_VERSION_INVALID", "页面版本不匹配")
    sections = _sections(session, version_id)
    snapshot_state = wiki_version_state(session, version_id)

    def dependency_state(section: dict[str, Any]) -> dict[str, Any]:
        checked = validate_dependencies(
            session, project_id, section["dependencies"], include_personal, purpose
        )
        if not require_local or purpose == "local":
            return checked
        local = validate_dependencies(
            session, project_id, section["dependencies"], include_personal, "local"
        )
        # HTTP responses require both uses; model permission cannot restore locally hidden text.
        states = {checked["content_state"], local["content_state"]}
        local_roots = {digest(root) for root in local["roots"]}
        return {
            "content_state": next(
                state for state in ("invalid", "stale", "unverified", "valid") if state in states
            ),
            "issues": sorted(set(checked["issues"]) | set(local["issues"])),
            "roots": [root for root in checked["roots"] if digest(root) in local_roots],
        }

    visible_sections = []
    states = set()
    for section in sections:
        checked = dependency_state(section)
        if snapshot_state:
            checked = {
                **checked,
                "content_state": "invalid",
                "issues": [*checked["issues"], *snapshot_state["issues"]],
            }
        if section["stale_reason"] and checked["content_state"] == "valid":
            checked = {**checked, "content_state": "stale", "issues": ["WIKI_SECTION_MARKED_STALE"]}
        states.add(checked["content_state"])
        # Unauthorized, missing and invalid source content must not leak through cached Markdown.
        personal_denied = any("NOTE" in issue for issue in checked["issues"])
        denied = personal_denied or checked["content_state"] == "invalid"
        text = "" if denied else section["text"]
        visible_sections.append(
            {
                **section,
                "text": text,
                "heading": "" if denied else section["heading"],
                "caveats": [] if denied else section["caveats"],
                "conditions": [] if denied else section["conditions"],
                "links": [] if denied else section["links"],
                "stale_reason": None if denied else section["stale_reason"],
                "content_state": checked["content_state"],
                "issues": checked["issues"],
                "stale": checked["content_state"] != "valid",
                "roots": checked["roots"] if not personal_denied else [],
            }
        )
    hidden = any(a["text"] != b["text"] for a, b in zip(visible_sections, sections, strict=True))
    if snapshot_state:
        states.add("invalid")
    title = "部分来源未获授权或不可用" if hidden or snapshot_state else wiki.title
    # Render from currently validated roots instead of trusting cached Markdown/reference bytes.
    # This also keeps revoked note quotes and corrupt render snapshots out of GET responses.
    refs, section_refs = _derive_references(
        session, project_id, [s for s in visible_sections if s["text"]]
    )
    markdown = render_markdown(
        page_id, title, visible_sections, refs, section_refs, wiki.content_hash
    )
    versions = list(
        session.execute(
            select(QueryDocumentVersion, WikiVersion)
            .join(WikiVersion, WikiVersion.version_id == QueryDocumentVersion.id)
            .where(QueryDocumentVersion.document_id == page_id)
            .order_by(QueryDocumentVersion.revision.desc())
        )
    )
    if require_local:
        versions = [
            row
            for row in versions
            if not any(
                issue.endswith("NOT_AUTHORIZED")
                for section in _sections(session, row[0].id)
                for issue in dependency_state(section)["issues"]
            )
        ]
    base = session.get(WikiVersion, wiki.base_version_id) if wiki.base_version_id else None
    base_hidden = False
    base_markdown = ""
    if base:
        base_sections = _sections(session, base.version_id)
        base_hidden = bool(wiki_version_state(session, base.version_id)) or any(
            dependency_state(s)["content_state"] != "valid" for s in base_sections
        )
        if not base_hidden:
            base_refs, base_section_refs = _derive_references(session, project_id, base_sections)
            base_markdown = render_markdown(
                page_id, base.title, base_sections, base_refs, base_section_refs, base.content_hash
            )
    # An unauthorized previous version must not leak through a unified diff.
    diff = (
        ""
        if hidden or snapshot_state or base_hidden
        else "".join(
            difflib.unified_diff(
                base_markdown.splitlines(keepends=True),
                markdown.splitlines(keepends=True),
                fromfile="base.md",
                tofile="draft.md",
            )
        )
    )
    from researchgraph.wiki_models import WikiPublication
    from researchgraph.wiki_publish import file_status, publication_view

    file = file_status(session, project_id, page_id)
    return {
        "page_id": page_id,
        "title": title,
        "version_id": version.id,
        "head_version_id": page.head_version_id,
        "saved_version_id": document.current_version_id,
        "revision": version.revision,
        "state": version.state,
        "content_hash": wiki.content_hash,
        "content_state": "invalid"
        if "invalid" in states
        else "stale"
        if "stale" in states
        else "unverified"
        if "unverified" in states
        else "valid",
        "markdown": markdown,
        "sections": visible_sections,
        "affected_section_ids": [s["section_id"] for s in visible_sections if s["stale"]],
        "versions": [
            {
                "version_id": v.id,
                "revision": v.revision,
                "state": v.state,
                "content_hash": w.content_hash,
            }
            for v, w in versions
        ],
        "diff": diff,
        "file": file,
        "file_state": file["state"],
        "published_version_id": file.get("version_id"),
        "publications": [
            publication_view(p)
            for p in session.scalars(
                select(WikiPublication)
                .where(WikiPublication.document_id == page_id)
                .order_by(WikiPublication.created_at.desc(), WikiPublication.id.desc())
            )
        ],
    }


class WikiMutations:
    def __init__(self, store: KnowledgeStore):
        self.store, self.session = store, store.session

    def _remembered(self, key: str, request: Any) -> dict[str, Any] | None:
        previous = self.session.get(QueryOperation, key)
        if previous:
            if previous.request_hash != digest(request):
                raise KnowledgeError("IDEMPOTENCY_CONFLICT", "操作标识已用于不同的页面请求")
            return previous.response
        return None

    def _record(self, key: str, request: Any, result: dict[str, Any]) -> dict[str, Any]:
        self.session.add(QueryOperation(key=key, request_hash=digest(request), response=result))
        return result

    def _checked_version(
        self, page_id: str, version_id: str, *, saveable: bool = False
    ) -> WikiVersion:
        version = self.session.get(QueryDocumentVersion, version_id)
        wiki = self.session.get(WikiVersion, version_id)
        if not version or version.document_id != page_id or not wiki:
            raise KnowledgeError("WIKI_VERSION_INVALID", "页面版本不匹配")
        if wiki_version_state(self.session, version_id):
            raise KnowledgeError("WIKI_SNAPSHOT_INVALID", "页面快照完整性已变化，拒绝重新绑定内容")
        if saveable:
            document = self.session.get(QueryDocument, page_id)
            assert document
            for section in _sections(self.session, version_id):
                state = validate_dependencies(
                    self.session, document.project_id, section["dependencies"], True, "local"
                )
                if section["stale_reason"] or state["content_state"] != "valid":
                    raise KnowledgeError(
                        "WIKI_CONTENT_STALE", "过期或失效依据的段落不能保存为当前有效版本"
                    )
        return wiki

    def _new_version(
        self,
        project_id: str,
        title: str,
        sections: list[dict[str, Any]],
        provenance: dict[str, Any],
        key: str,
        page_id: str | None = None,
        state: Literal["draft", "saved"] = "draft",
        base_version_id: str | None = None,
    ) -> dict[str, Any]:
        document = self.session.get(QueryDocument, page_id) if page_id else None
        for section in sections:
            for linked in section["links"]:
                _scope(self.session, project_id, linked)
        passages = [
            DocumentPassageInput(
                local_ref=s["section_id"],
                text=s["text"],
                attribution=s["attribution"],
                dependencies=s["dependencies"],
                caveats=s["caveats"],
            )
            for s in sections
        ]
        # Match the canonical dependency bytes actually persisted by the shared Store.
        sections = [
            {
                **section,
                "dependencies": [d.model_dump(exclude_none=True) for d in passage.dependencies],
            }
            for section, passage in zip(sections, passages, strict=True)
        ]
        result = self.store.query().save_document(
            DocumentSaveRequest(
                project_id=project_id,
                kind="wiki",
                title=title,
                document_id=page_id,
                base_version_id=document.current_version_id if document else None,
                passages=passages,
                state=state,
            ),
            "wiki-document:" + key,
            preserve_version_id=base_version_id if state == "draft" else None,
        )
        page_id = result["document_id"]
        content_hash = digest(_semantic(title, sections))
        references, section_refs = _derive_references(self.session, project_id, sections)
        wiki = WikiVersion(
            version_id=result["version_id"],
            title=title,
            content_hash=content_hash,
            markdown=render_markdown(
                page_id, title, sections, references, section_refs, content_hash
            ),
            references=references,
            provenance=provenance,
            base_version_id=base_version_id,
        )
        self.session.add(wiki)
        for section, pid in zip(sections, result["passage_ids"], strict=True):
            self.session.add(
                WikiSection(
                    passage_id=pid,
                    version_id=result["version_id"],
                    section_id=section["section_id"],
                    heading=section["heading"],
                    conditions=section["conditions"],
                    links=section["links"],
                    stale_reason=section.get("stale_reason"),
                )
            )
        page = self.session.get(WikiPage, page_id)
        if page:
            page.head_version_id = result["version_id"]
        else:
            self.session.add(
                WikiPage(
                    document_id=page_id, head_version_id=result["version_id"], created_at=now()
                )
            )
        self.session.flush()
        return {
            "page_id": page_id,
            "version_id": result["version_id"],
            "content_hash": content_hash,
        }

    def create_draft(self, project_id: str, request: Any, key: str) -> dict[str, Any]:
        body = WikiDraftInput.model_validate(request)
        key = f"wiki-create:{project_id}:{key}"
        payload = body.model_dump()
        if previous := self._remembered(key, payload):
            return previous
        if not self.session.get(Project, project_id):
            raise KnowledgeError("PROJECT_NOT_FOUND", "项目不存在")
        sections = []
        for p in body.passages:
            value = p.model_dump(exclude={"local_ref"})
            sections.append({**value, "section_id": str(uuid4()), "stale_reason": None})
        result = self._new_version(project_id, body.title, sections, body.provenance, key)
        return self._record(key, payload, result)

    def apply_patch(self, project_id: str, page_id: str, request: Any, key: str) -> dict[str, Any]:
        body = WikiPatchInput.model_validate(request)
        key = f"wiki-patch:{project_id}:{page_id}:{key}"
        payload = body.model_dump()
        _, page = _scope(self.session, project_id, page_id)
        base = self._checked_version(page_id, body.base_version_id)
        if previous := self._remembered(key, payload):
            self._checked_version(page_id, previous["version_id"])
            return previous
        if (
            page.head_version_id != body.base_version_id
            or base.content_hash != body.base_content_hash
        ):
            raise KnowledgeError("WIKI_BASE_CONFLICT", "页面版本或内容基线已变化")
        sections = _sections(self.session, body.base_version_id)
        touched: set[str] = set()
        for edit in body.operations:
            target = edit.after_section_id if edit.op == "append" else edit.section_id
            indices = {s["section_id"]: i for i, s in enumerate(sections)}
            if target is not None and target not in indices:
                raise KnowledgeError("WIKI_SECTION_INVALID", "补丁引用了本页以外的段落")
            if edit.op == "append":
                value = edit.passage.model_dump(exclude={"local_ref"})
                new = {**value, "section_id": str(uuid4()), "stale_reason": None}
                sections.insert(indices[target] + 1 if target else len(sections), new)
                continue
            if target in touched:
                raise KnowledgeError("WIKI_PATCH_CONFLICT", "同一补丁不能多次修改同一段落")
            touched.add(edit.section_id)
            if edit.op == "replace":
                value = edit.passage.model_dump(exclude={"local_ref"})
                sections[indices[edit.section_id]] = {
                    **value,
                    "section_id": edit.section_id,
                    "stale_reason": None,
                }
            else:
                sections[indices[edit.section_id]]["stale_reason"] = edit.reason
        result = self._new_version(
            project_id,
            base.title,
            sections,
            body.provenance,
            key,
            page_id,
            base_version_id=body.base_version_id,
        )
        return self._record(key, payload, result)

    def save_draft(self, project_id: str, page_id: str, request: Any, key: str) -> dict[str, Any]:
        body = WikiSaveCommand.model_validate(request)
        key = f"wiki-save:{project_id}:{page_id}:{key}"
        payload = body.model_dump()
        document, page = _scope(self.session, project_id, page_id)
        wiki = self._checked_version(page_id, body.version_id, saveable=True)
        if previous := self._remembered(key, payload):
            self._checked_version(page_id, previous["version_id"], saveable=True)
            return previous
        if (
            page.head_version_id != body.expected_head_version_id
            or body.version_id != page.head_version_id
            or wiki.content_hash != body.expected_content_hash
        ):
            raise KnowledgeError("WIKI_BASE_CONFLICT", "保存目标已被其他草稿更新")
        sections = _sections(self.session, body.version_id)
        if document.current_version_id == body.version_id:
            result = {
                "page_id": page_id,
                "version_id": body.version_id,
                "content_hash": wiki.content_hash,
            }
        else:
            result = self._new_version(
                project_id,
                wiki.title,
                sections,
                wiki.provenance,
                key,
                page_id,
                state="saved",
                base_version_id=body.version_id,
            )
        return self._record(key, payload, result)

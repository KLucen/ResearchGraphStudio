"""Deterministic bilingual candidate recall over saved knowledge, never canvas data."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session


def terms(text: str) -> set[str]:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    words = set(re.findall(r"[a-z][a-z0-9_-]{2,}", normalized))
    words -= {"the", "and", "for", "with", "this", "that", "from", "paper", "study", "research"}
    for chinese in re.findall(r"[\u3400-\u9fff]+", normalized):
        words.update(chinese[i : i + 2] for i in range(len(chinese) - 1))
    return words


def knowledge_text(content: dict[str, Any], title: str) -> str:
    fields = [title]
    for node in content.get("graph", {}).get("nodes", []):
        if node.get("type") != "PAPER":
            fields.extend(
                str(node.get(key) or "") for key in ("label_zh", "label_en", "description_zh")
            )
    card = content.get("paper_card", {})
    for value in card.values():
        fields.extend(str(item) for item in value) if isinstance(value, list) else fields.append(
            str(value)
        )
    return " ".join(fields)


def retrieve_candidates(
    db: Session, version: Any, settings: dict[str, Any]
) -> tuple[list[Any], dict[str, Any]]:
    from researchgraph.knowledge_library_models import (
        KnowledgeCollectionMember,
        LibraryPaper,
        LibraryPaperSourceLink,
        PaperKnowledgeVersion,
    )

    rows = db.execute(
        select(LibraryPaper, PaperKnowledgeVersion)
        .join(PaperKnowledgeVersion, LibraryPaper.current_version_id == PaperKnowledgeVersion.id)
        .where(LibraryPaper.archived.is_(False), LibraryPaper.id != version.library_paper_id)
    ).all()
    collection_id = settings.get("collection_id")
    memberships = (
        set(
            db.scalars(
                select(KnowledgeCollectionMember.library_paper_id).where(
                    KnowledgeCollectionMember.collection_id == collection_id
                )
            ).all()
        )
        if collection_id
        else set()
    )
    project_members = set(
        db.scalars(
            select(LibraryPaperSourceLink.library_paper_id).where(
                LibraryPaperSourceLink.project_id == version.project_id
            )
        ).all()
    )
    eligible = [
        (paper, candidate)
        for paper, candidate in rows
        if (
            settings.get("scope", "project") == "all"
            or settings.get("scope") == "collection"
            and paper.id in memberships
            or settings.get("scope", "project") == "project"
            and paper.id in project_members
        )
    ]
    origin = db.get(LibraryPaper, version.library_paper_id)
    source_terms = terms(knowledge_text(version.content_json, origin.title if origin else ""))
    scored = []
    excluded = 0
    for paper, candidate in eligible:
        if candidate.evidence_status != "grounded":
            excluded += 1
            continue
        candidate_terms = terms(knowledge_text(candidate.content_json, paper.title))
        shared = source_terms & candidate_terms
        if shared:
            score = len(shared) / max(1, min(len(source_terms), len(candidate_terms)))
            scored.append((score, candidate.created_at, candidate.id, candidate))
    scored.sort(key=lambda row: (-row[0], row[1], row[2]))
    selected = [row[3] for row in scored[: settings.get("max_candidates", 8)]]
    return selected, {
        "scope": settings.get("scope", "project"),
        "eligible": len(eligible),
        "selected": len(selected),
        "compared": 0,
        "excluded_legacy": excluded,
        "candidate_count": len(scored),
        "retrieval_policy": "knowledge-bilingual-terms-1",
        "not_compared": len(eligible) - len(selected),
    }

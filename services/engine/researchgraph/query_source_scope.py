"""Read-only paper identities for Query display filters; frozen payloads stay unchanged."""

from collections.abc import Iterable
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from researchgraph.models import Paper
from researchgraph.query_models import QueryAnswerVersion, QueryRun


def paper_ids_from_sources(
    sources: Iterable[dict[str, Any]],
    allowed: set[str],
    version_papers: dict[str, str] | None = None,
) -> list[str]:
    """Use explicit root identity, never the question's whole requested paper scope."""
    result: set[str] = set()
    versions = version_papers or {}
    for source in sources:
        pid = source.get("paper_id")
        if source.get("type") == "paper":
            pid = source.get("id")
        if not pid:
            pid = versions.get(source.get("document_version_id", ""))
        if isinstance(pid, str) and pid in allowed:
            result.add(pid)
        roots = source.get("roots", [])
        if isinstance(roots, list):
            result.update(
                paper_ids_from_sources((r for r in roots if isinstance(r, dict)), allowed, versions)
            )
    return sorted(result)


def query_paper_ids(session: Session, run: QueryRun) -> list[str]:
    """Completed history follows actually cited roots; prepared history follows its context."""
    allowed = set(session.scalars(select(Paper.id).where(Paper.project_id == run.project_id)))
    context = run.snapshot.get("context", {})
    sources = [r for r in context.get("references", []) if isinstance(r, dict)]
    answer = session.scalar(
        select(QueryAnswerVersion)
        .where(QueryAnswerVersion.query_run_id == run.id)
        .order_by(QueryAnswerVersion.revision.desc())
        .limit(1)
    )
    if answer is not None:
        cited = {
            ref
            for passage in answer.data.get("passages", [])
            for ref in passage.get("source_refs", [])
        }
        sources = [r for r in sources if r.get("ref") in cited]
    versions = {
        v["id"]: v["paper_id"]
        for v in context.get("source_versions", [])
        if isinstance(v, dict) and isinstance(v.get("id"), str) and v.get("paper_id") in allowed
    }
    return paper_ids_from_sources(sources, allowed, versions)

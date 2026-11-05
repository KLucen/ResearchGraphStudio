"""Saved-reading library lifecycle, independent of scientific truth or model history."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from researchgraph.knowledge_store import digest, text_hash
from researchgraph.query_contracts import QueryAnswer, QueryDependency
from researchgraph.query_models import QueryAnswerVersion, QueryModelRun, QueryRun
from researchgraph.query_saved_models import QuerySavedKnowledge, QuerySavedPreference


def reference_dependency(reference: dict[str, Any]) -> dict[str, Any] | None:
    kind = reference["type"]
    if kind == "paper":
        return None  # A title alone supplies metadata, never scientific support.
    fields = ["type", "id", "revision"] if kind == "node" else ["type", "id", "sha256"]
    if kind == "chunk":
        fields += ["start", "end", "quote"]
    result = {k: reference[k] for k in fields}
    if kind == "node":
        result["sha256"] = text_hash(reference["text"])
        result["payload_sha256"] = reference["payload_hash"]
    QueryDependency.model_validate(result)
    return result


def answer_lineage_hash(session: Session, answer: QueryAnswerVersion) -> str:
    model = session.get(QueryModelRun, answer.model_run_id) if answer.model_run_id else None
    return digest(
        None
        if model is None
        else {
            "id": model.id,
            "project_id": model.project_id,
            "query_run_id": model.query_run_id,
            "provider": model.provider,
            "model": model.model,
            "prompt_name": model.prompt_name,
            "input_hash": model.input_hash,
            "prompt_hash": model.prompt_hash,
            "manifest": model.manifest,
            "schema_version": model.schema_version,
            "raw_output": model.raw_output,
            "status": model.status,
            "model_snapshot": model.parameters.get("model_snapshot"),
            "dispatch": model.parameters.get("dispatch"),
            "raw_sha256": model.parameters.get("raw_sha256"),
            "raw_complete": model.parameters.get("raw_complete"),
            **(
                {"display_normalization": model.parameters["display_normalization"]}
                if "display_normalization" in model.parameters
                else {}
            ),
        }
    )


def passage_lineage(
    session: Session, saved: QuerySavedKnowledge, original: dict[str, Any]
) -> dict[str, Any]:
    """Recover pre-0014 wrapper dependencies without rewriting any frozen record."""
    try:
        if "lineage_dependencies" in original:
            dependencies = original["lineage_dependencies"]
            if not isinstance(dependencies, list):
                raise ValueError("invalid lineage dependencies")
            for dependency in dependencies:
                QueryDependency.model_validate(dependency)
        else:
            query = session.get(QueryRun, saved.source_query_id)
            answer = session.get(QueryAnswerVersion, saved.answer_version_id)
            if (
                query is None
                or answer is None
                or query.project_id != saved.project_id
                or answer.project_id != saved.project_id
                or answer.query_run_id != query.id
                or answer.state != "validated"
                or saved.input_hash != query.input_hash
                or answer.input_hash != query.input_hash
            ):
                raise ValueError("invalid original answer scope")
            context = query.snapshot["context"]
            unhashed = {k: v for k, v in context.items() if k != "input_hash"}
            if (
                context["project_id"] != saved.project_id
                or context["request"]["project_id"] != saved.project_id
                or query.request["project_id"] != saved.project_id
                or context["input_hash"] != query.input_hash
                or digest(unhashed) != query.input_hash
                or saved.manifest["source_query_id"] != query.id
                or saved.manifest["answer_version_id"] != answer.id
                or saved.manifest["input_hash"] != query.input_hash
                or saved.manifest["source_context_hash"] != digest(context)
                or saved.manifest["answer_hash"] != digest(answer.data)
                or saved.manifest["model_lineage_hash"] != answer_lineage_hash(session, answer)
            ):
                raise ValueError("invalid frozen answer lineage")
            data = QueryAnswer.model_validate(answer.data)
            if (
                data.answer_version_id != answer.id
                or data.query_run_id != query.id
                or data.input_hash != query.input_hash
                or data.revision != answer.revision
                or data.status != "validated"
                or data.knowledge_status == "insufficient"
            ):
                raise ValueError("invalid original answer identity")
            passage = next(p for p in data.passages if p.local_ref == original["answer_local_ref"])
            if (
                passage.local_ref not in saved.selected_passage_refs
                or original["document_local_ref"] != f"query-{answer.id}-{passage.local_ref}"
                or original["text_hash"] != text_hash(passage.text)
                or original["attribution"] != passage.attribution
                or original["caveats"] != passage.caveats
                or original["source_refs"] != passage.source_refs
            ):
                raise ValueError("invalid saved passage identity")
            references = {r["ref"]: r for r in context["references"]}
            if len(references) != len(context["references"]):
                raise ValueError("duplicate frozen references")
            dependencies = [
                dependency
                for ref in passage.source_refs
                if (dependency := reference_dependency(references[ref])) is not None
            ]
            if not dependencies:
                raise ValueError("missing original source dependencies")
        return {"lineage_dependencies": list({digest(d): d for d in dependencies}.values())}
    except (KeyError, TypeError, ValueError, AttributeError, StopIteration):
        return {"lineage_dependencies": [], "lineage_issue": "QUERY_SAVED_LINEAGE_INVALID"}


def saved_passage_states(
    session: Session, project_id: str
) -> dict[tuple[str, str], dict[str, Any]]:
    """Local refs survive document appends, so removed text cannot reappear in later copies."""
    result: dict[tuple[str, str], dict[str, Any]] = {}
    rows = session.execute(
        select(QuerySavedKnowledge, QuerySavedPreference)
        .outerjoin(QuerySavedPreference, QuerySavedPreference.saved_id == QuerySavedKnowledge.id)
        .where(QuerySavedKnowledge.project_id == project_id)
    )
    for saved, preference in rows:
        for passage in saved.manifest.get("passages", []):
            local_ref = passage.get("document_local_ref")
            if not isinstance(local_ref, str):
                continue
            result[(saved.document_id, local_ref)] = {
                "removed": bool(preference and preference.removed_at),
                **passage_lineage(session, saved, passage),
            }
    return result

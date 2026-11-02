"""Current reading candidates, separate from retained legacy graph history."""

from typing import Any

from pydantic import TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from researchgraph.knowledge_models import KnowledgeNode, ModelRun
from researchgraph.reading_contracts import Candidate

CONTRACT = "reading-extraction-1.0"
SCOPE = "reading-candidates-only-v1"
_candidate = TypeAdapter(Candidate)


def current_candidate(node: KnowledgeNode, run: ModelRun | None) -> bool:
    if (
        not run
        or run.schema_version != "reading-1.0"
        or not run.prompt_name.startswith("P02_reading")
    ):
        return False
    try:
        _candidate.validate_python(node.payload)
    except (ValidationError, TypeError):
        return False
    return True


def current_nodes(session: Session, version_id: str) -> list[KnowledgeNode]:
    return [
        node
        for node, run in session.execute(
            select(KnowledgeNode, ModelRun)
            .join(ModelRun, ModelRun.id == KnowledgeNode.model_run_id)
            .where(KnowledgeNode.document_version_id == version_id)
            .order_by(KnowledgeNode.id)
        )
        if current_candidate(node, run)
    ]


def current_selection(selection: Any) -> bool:
    return bool(selection and selection.data.get("candidate_scope") == SCOPE)

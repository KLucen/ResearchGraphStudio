"""Hide untouched historical test fixtures without deleting user knowledge."""

from sqlalchemy import or_, select
from sqlalchemy.sql.elements import ColumnElement

from researchgraph.knowledge_models import KnowledgeNode, ModelRun


def production_knowledge() -> ColumnElement[bool]:
    return or_(
        KnowledgeNode.model_run_id.is_(None),
        KnowledgeNode.model_run_id.not_in(select(ModelRun.id).where(ModelRun.provider == "mock")),
        KnowledgeNode.review_status == "accepted",
        KnowledgeNode.revision > 1,
    )

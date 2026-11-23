"""Guard active workspace actions without changing stored source provenance."""

from fastapi import HTTPException
from sqlalchemy.orm import Session

from researchgraph.archive_models import archived_target


def require_unarchived_paper(db: Session, paper_id: object) -> None:
    if isinstance(paper_id, str) and archived_target(db, "paper", paper_id):
        raise HTTPException(
            409,
            {"code": "PAPER_ARCHIVED", "message": "请先在归档管理中恢复该论文"},
        )

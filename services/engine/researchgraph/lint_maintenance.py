"""Bounded worker entry point for opt-in deterministic dependency diagnostics."""

import time

from sqlalchemy import Engine, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from researchgraph.knowledge_store import KnowledgeError, KnowledgeStore
from researchgraph.lint_models import DependencyCursor, LintRun
from researchgraph.lint_service import LintStore, _sequence
from researchgraph.storage import read_session

# Scheduling only, never a source/permission/validation cache. Periodic reconciliation also
# recovers legacy writes or missed Events; every chosen reconciliation re-reads all inputs.
_last_attempt: dict[tuple[str, str], float] = {}
RECONCILE_INTERVAL = 30.0


def reconcile_pending(engine: Engine) -> None:
    """Reconcile only projects enabled by an existing dependency cursor."""
    stamp = time.monotonic()
    with read_session(engine) as session, session.begin():
        cursors = list(
            session.execute(select(DependencyCursor.project_id, DependencyCursor.event_sequence))
        )
        active = {
            project_id
            for project_id, scope in session.execute(
                select(LintRun.project_id, LintRun.scope).where(
                    LintRun.status.in_({"queued", "running"})
                )
            )
            if scope.get("incremental")
        }
        due = [
            project_id
            for project_id, event_sequence in cursors
            if project_id in active
            or _sequence(session, project_id) > event_sequence
            or stamp - _last_attempt.get((str(engine.url), project_id), float("-inf"))
            >= RECONCILE_INTERVAL
        ]
    # One project's bounded advance per worker tick keeps the rest of the engine responsive.
    if not due:
        return
    project_id = min(due, key=lambda p: _last_attempt.get((str(engine.url), p), float("-inf")))
    try:
        with Session(engine) as session, session.begin():
            LintStore(KnowledgeStore(session)).reconcile(project_id, max_items=25)
    except (KnowledgeError, SQLAlchemyError, OSError):
        # The transaction rolls back, including the cursor. Nothing has been acknowledged;
        # the next event-driven tick or periodic reconciliation can safely resume.
        return
    _last_attempt[(str(engine.url), project_id)] = stamp

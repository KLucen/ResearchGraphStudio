from uuid import uuid4

from fastapi.testclient import TestClient
from researchgraph.app import create_app
from researchgraph.models import Job, Project, now
from sqlalchemy.orm import Session


def test_job_history_projects_reading_task_without_exposing_frozen_payload(tmp_path):
    token = "synthetic-test-token" * 3
    app = create_app(tmp_path, token, start_worker=False)
    cases = [
        ("paper_overview", {"overview_contract_version": 2}, "paper_card_set"),
        ("paper_overview", {}, None),
        ("llm_document_postprocess", {"item_kind": "paper_overview"}, "paper_overview"),
        *[
            (
                "llm_document_postprocess",
                {"item_kind": "paper_overview", "postprocess_contract_version": version},
                "paper_card_set",
            )
            for version in (5, 6)
        ],
        ("llm_document_postprocess", {"item_kind": "paper_reading"}, "paper_reading"),
        ("llm_document_postprocess", {"item_kind": "translation"}, "translation"),
        ("llm_document_postprocess", {"item_kind": "synthetic-unsupported"}, None),
        ("diagnostics", {"item_kind": "translation"}, None),
    ]
    project_id = str(uuid4())
    frozen_private = "SYNTHETIC_PRIVATE_FROZEN_VALUE"
    with TestClient(app, headers={"Authorization": f"Bearer {token}"}) as client:
        expected = {}
        timestamp = now()
        with Session(app.state.engine) as db, db.begin():
            db.add(Project(id=project_id, name="Fixture", description="", created_at=timestamp))
            db.flush()
            for kind, payload, reading_task in cases:
                job_id = str(uuid4())
                expected[job_id] = reading_task
                db.add(
                    Job(
                        id=job_id,
                        project_id=project_id,
                        kind=kind,
                        payload={**payload, "provider_snapshot": {"secret": frozen_private}},
                        status="failed",
                        stage="failed",
                        created_at=timestamp,
                        updated_at=timestamp,
                    )
                )
        all_jobs = client.get("/api/v1/jobs")
        project_jobs = client.get(f"/api/v1/projects/{project_id}/jobs")
        for response, rows in (
            (all_jobs, all_jobs.json()),
            (project_jobs, project_jobs.json()["items"]),
        ):
            assert response.status_code == 200
            assert frozen_private not in response.text
            assert {row["id"]: row["reading_task"] for row in rows} == expected
        for job_id, name in expected.items():
            detail = client.get(f"/api/v1/jobs/{job_id}")
            assert detail.status_code == 200 and detail.json()["reading_task"] == name
            assert frozen_private not in detail.text

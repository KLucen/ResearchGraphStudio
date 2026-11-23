import pytest
from researchgraph.import_plan_models import ImportPlanItem, ImportSession
from researchgraph.models import Job
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_engine import client, post
from test_paper_management_api import add_paper


@pytest.mark.parametrize("legacy_import", [False, True])
def test_archived_paper_blocks_saved_reading_urls_and_job_retries(tmp_path, legacy_import):
    with client(tmp_path) as api:
        ids = add_paper(api, tmp_path)
        paper = f"/papers/{ids['paper_id']}"
        section = f"{paper}/sections/{ids['section_id']}"
        project = f"/projects/{ids['project_id']}"
        source = f"/import-sessions/{ids['session_id']}"
        with Session(api.app.state.engine) as db, db.begin():
            if legacy_import:
                session = db.get(ImportSession, ids["session_id"])
                session.source_snapshot = {
                    key: value
                    for key, value in session.source_snapshot.items()
                    if key != "paper_id"
                }
            item = db.scalar(
                select(ImportPlanItem).where(
                    ImportPlanItem.session_id == ids["session_id"],
                    ImportPlanItem.item_kind == "document_parse",
                )
            )
            job_id = item.job_id
            item.status = db.get(Job, job_id).status = "failed"
            job_count = db.scalar(select(func.count(Job.id)))

        assert api.get("/api/v1" + source + "/document-parse").status_code == 200
        staged = post(api, "/archive", {"kind": "paper", "target_id": ids["paper_id"]})
        assert staged.status_code == 200, staged.text
        item_id = staged.json()["id"]

        for path in [
            source,
            source + "/document-parse",
            source + "/document-outputs",
            source + "/chapter-reading-states",
            paper + "/overview",
            paper + f"/model-overview?parse_id={ids['parse_id']}",
            paper + "/reading-notes",
            paper + "/section-guides",
            paper + "/qa",
            paper + "/qa/keywords",
        ]:
            response = api.get("/api/v1" + path)
            assert response.status_code == 409, (path, response.text)
            assert response.json()["error"]["code"] == "PAPER_ARCHIVED"
        assert api.get("/api/v1" + project + "/import-sessions").json() == []

        for index, (path, body) in enumerate(
            [
                (paper + "/overview/generate", {}),
                (paper + "/model-overview/generate", {"document_version_id": ids["parse_id"]}),
                (paper + "/reading-notes/generate", {}),
                (section + "/guide/generate", {"section_id": ids["section_id"]}),
                (section + "/close-reading/generate", {"paragraph_ids": [ids["chunk_id"]]}),
                (
                    section + "/understanding-check/generate",
                    {"paragraph_ids": [ids["chunk_id"]], "user_explanation": "Test claim"},
                ),
                (paper + "/qa/ask", {"question": "What was tested?"}),
                (paper + "/qa/keywords", {"question": "What was tested?"}),
                (source + "/document-outputs/paper_reading/generate", {}),
                (source + "/document-outputs/stale-output/format-repair", {}),
            ]
        ):
            response = post(api, path, {"allow_network": True, **body}, key=f"stale-{index:03}")
            assert response.status_code == 409, (path, response.text)
            assert response.json()["error"]["code"] == "PAPER_ARCHIVED"

        for path in [source + "/items/document_parse/retry", f"/jobs/{job_id}/retry"]:
            response = post(api, path)
            assert response.status_code == 409, response.text
            assert response.json()["error"]["code"] == "PAPER_ARCHIVED"
        response = post(
            api,
            project + "/import-sessions",
            {
                "selection_id": "stale-import-selection",
                "source_snapshot": {"file_name": "test.pdf", "paper_id": ids["paper_id"]},
                "plan": {},
            },
        )
        assert response.status_code == 409, response.text
        assert response.json()["error"]["code"] == "PAPER_ARCHIVED"

        with Session(api.app.state.engine) as db:
            assert db.scalar(select(func.count(Job.id))) == job_count
            assert db.get(Job, job_id).status == "failed"

        assert post(api, f"/archive/{item_id}/restore").status_code == 200
        assert api.get("/api/v1" + source + "/document-parse").status_code == 200
        sessions = api.get("/api/v1" + project + "/import-sessions").json()
        assert [session["id"] for session in sessions] == [ids["session_id"]]

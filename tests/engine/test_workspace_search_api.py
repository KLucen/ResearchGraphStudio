from uuid import uuid4

from researchgraph.models import Paper, Project, now
from sqlalchemy.orm import Session
from test_engine import client, post


def test_workspace_search_reaches_later_projects_and_papers(tmp_path):
    with client(tmp_path) as api:
        with Session(api.app.state.engine) as db, db.begin():
            projects = [
                Project(
                    id=str(uuid4()),
                    name=f"合成项目 {index:02}",
                    description="可搜索的项目说明" if index == 0 else "",
                    created_at=f"2026-11-01T00:{index:02}Z",
                )
                for index in range(52)
            ]
            db.add_all(projects)
            db.flush()
            outsider = projects[0].id
            papers = [
                Paper(
                    id=str(uuid4()),
                    project_id=outsider,
                    title=f"Graph {index:02}",
                    created_at=now(),
                )
                for index in range(52)
            ]
            literal = Paper(
                id=str(uuid4()), project_id=outsider, title="Literal %_ paper", created_at=now()
            )
            db.add_all([*papers, literal])
            archived, old = papers.pop(), papers[0]
            archived_id, old_id, literal_id = archived.id, old.id, literal.id
        assert outsider not in {
            project["id"] for project in api.get("/api/v1/projects").json()["items"]
        }
        assert post(api, "/archive", {"kind": "paper", "target_id": archived_id}).status_code == 200

        found = api.get("/api/v1/workspace/search", params={"q": "项目说明"}).json()
        assert [hit["project"]["id"] for hit in found["items"]] == [outsider]
        path = "/api/v1/workspace/search"
        first = api.get(path, params={"q": "gRaPh", "limit": 50}).json()
        last = api.get(path, params={"q": "GRAPH", "offset": first["next_offset"]}).json()
        assert first["total"] == last["total"] == 51
        assert first["next_offset"] == 50 and last["next_offset"] is None
        found_papers = first["items"] + last["items"]
        assert len({result["id"] for result in found_papers}) == 51
        assert old_id in {result["id"] for result in found_papers}
        assert archived_id not in {result["id"] for result in found_papers}
        special = api.get(path, params={"q": "%_"}).json()
        assert [hit["id"] for hit in special["items"]] == [literal_id]
        assert api.get(path, params={"q": "   "}).json() == {
            "items": [],
            "total": 0,
            "next_offset": None,
        }
        assert api.get(path, params={"q": "a" * 201}).status_code == 422
        assert (
            api.get(path, params={"q": "Graph"}, headers={"Authorization": ""}).status_code == 401
        )
        assert api.get("/api/v1/jobs").json() == []

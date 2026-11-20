"""Local personal progress. Reading and writing this API never invoke a model."""

from collections.abc import Callable
from typing import Literal, cast
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import Field
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from researchgraph.chapter_reading_models import ModelChapterReadingState
from researchgraph.core import StrictModel
from researchgraph.import_plan_models import ImportSession
from researchgraph.model_document_models import LlmDocumentParse, LlmDocumentSegment
from researchgraph.models import now
from researchgraph.storage import read_session

Progress = Literal["NOT_STARTED", "READING", "COMPLETED"]


class ChapterReadingPut(StrictModel):
    parse_id: str = Field(min_length=1, max_length=36)
    chapter_ref: str = Field(min_length=1, max_length=160)
    progress: Progress


class ChapterReadingView(ChapterReadingPut):
    updated_at: str | None = None


class ChapterReadingList(StrictModel):
    parse_id: str
    items: list[ChapterReadingView]


def _current_parse(db: Session, session_id: str) -> LlmDocumentParse:
    if db.get(ImportSession, session_id) is None:
        raise HTTPException(404, {"code": "IMPORT_SESSION_NOT_FOUND", "message": "导入会话不存在"})
    parse = db.scalar(
        select(LlmDocumentParse)
        .where(LlmDocumentParse.import_session_id == session_id)
        .order_by(LlmDocumentParse.created_at.desc(), LlmDocumentParse.id.desc())
        .limit(1)
    )
    if parse is None:
        raise HTTPException(
            404, {"code": "DOCUMENT_PARSE_NOT_FOUND", "message": "尚无模型章节解析"}
        )
    return parse


def _major_chapters(db: Session, parse_id: str) -> list[str]:
    segments = list(
        db.scalars(
            select(LlmDocumentSegment)
            .where(LlmDocumentSegment.parse_id == parse_id)
            .order_by(
                LlmDocumentSegment.chapter_order,
                LlmDocumentSegment.chapter_level,
                LlmDocumentSegment.ordinal,
                LlmDocumentSegment.id,
            )
        )
    )
    if not segments:
        return []
    level = min(segment.chapter_level for segment in segments)
    return list(dict.fromkeys(s.chapter_ref for s in segments if s.chapter_level == level))


def register_chapter_reading_api(app: FastAPI, engine: Callable[[], Engine]) -> None:
    path = "/api/v1/import-sessions/{session_id}/chapter-reading-states"

    @app.get(path, response_model=ChapterReadingList)
    def get_states(session_id: str) -> ChapterReadingList:
        with read_session(engine()) as db:
            parse = _current_parse(db, session_id)
            chapters = _major_chapters(db, parse.id) if parse.status == "succeeded" else []
            rows = {
                row.chapter_ref: row
                for row in db.scalars(
                    select(ModelChapterReadingState).where(
                        ModelChapterReadingState.parse_id == parse.id
                    )
                )
            }
            return ChapterReadingList(
                parse_id=parse.id,
                items=[
                    ChapterReadingView(
                        parse_id=parse.id,
                        chapter_ref=ref,
                        progress=cast(Progress, rows[ref].progress)
                        if ref in rows
                        else "NOT_STARTED",
                        updated_at=rows[ref].updated_at if ref in rows else None,
                    )
                    for ref in chapters
                ],
            )

    @app.put(path, response_model=ChapterReadingView)
    def save_state(session_id: str, body: ChapterReadingPut) -> ChapterReadingView:
        with Session(engine()) as db, db.begin():
            parse = _current_parse(db, session_id)
            if parse.id != body.parse_id or parse.status != "succeeded":
                raise HTTPException(
                    409,
                    {
                        "code": "DOCUMENT_PARSE_CHANGED",
                        "message": "解析版本已变化，请刷新后标记阅读状态",
                    },
                )
            if body.chapter_ref not in _major_chapters(db, parse.id):
                raise HTTPException(
                    422,
                    {"code": "CHAPTER_NOT_FOUND", "message": "请选择当前解析结果中的大章节"},
                )
            row = db.scalar(
                select(ModelChapterReadingState).where(
                    ModelChapterReadingState.parse_id == parse.id,
                    ModelChapterReadingState.chapter_ref == body.chapter_ref,
                )
            )
            if row is None:
                row = ModelChapterReadingState(
                    id=str(uuid4()),
                    parse_id=parse.id,
                    chapter_ref=body.chapter_ref,
                    progress=body.progress,
                    updated_at=now(),
                )
                db.add(row)
            elif row.progress != body.progress:
                row.progress, row.updated_at = body.progress, now()
            return ChapterReadingView(**body.model_dump(), updated_at=row.updated_at)

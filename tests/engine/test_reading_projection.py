"""Anonymous PDFs exercise local layout without models or private Zotero data."""

import hashlib
from copy import deepcopy
from uuid import uuid4

import pymupdf
import pytest
from researchgraph.core import KnowledgeError, text_hash
from researchgraph.document_structure import apply_structure
from researchgraph.models import (
    AttachmentRevision,
    Base,
    Chunk,
    EvidenceSpan,
    Paper,
    PaperSource,
    Project,
    Section,
    now,
)
from researchgraph.pdf_structure import parse_structure
from researchgraph.reading_document_models import ReadingDocumentProjection
from researchgraph.reading_projection import build_reading_document
from researchgraph.structure_models import DocumentParse
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session


def store(document, tmp_path=None, *, legacy=False):
    content = document.tobytes()
    digest = hashlib.sha256(content).hexdigest()
    structure = parse_structure(document)
    if legacy:
        structure.pop("figures", None)
        structure.pop("page_geometry", None)
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    project_id, paper_id, revision_id = (str(uuid4()) for _ in range(3))
    with Session(engine) as session, session.begin():
        session.add(
            Project(
                id=project_id,
                name="fixture",
                description="",
                experience_mode="lite",
                created_at=now(),
            )
        )
        session.flush()
        session.add(Paper(id=paper_id, project_id=project_id, title="Synthetic", created_at=now()))
        session.flush()
        session.add(
            AttachmentRevision(
                id=revision_id,
                paper_id=paper_id,
                sha256=digest,
                parser_version="fixture",
                page_count=len(document),
                warnings=[],
                created_at=now(),
            )
        )
        session.flush()
        for block in structure["blocks"]:
            session.add(
                Chunk(
                    id=str(uuid4()),
                    revision_id=revision_id,
                    page_index=block["page_index"],
                    page_label="",
                    block_index=block["block_index"],
                    text=block["text"],
                    bbox=block["bbox"],
                )
            )
        session.flush()
        apply_structure(session, revision_id, digest, structure)
        if tmp_path:
            path = tmp_path / "anonymous.pdf"
            path.write_bytes(content)
            session.add(
                PaperSource(
                    id=str(uuid4()),
                    paper_id=paper_id,
                    revision_id=revision_id,
                    path=str(path),
                    mode="reference",
                    generation=1,
                    last_check=None,
                )
            )
    return engine, paper_id, revision_id


def textbox(page, x, y, text, width=230, size=11):
    assert page.insert_textbox((x, y, x + width, y + 120), text, fontsize=size) >= 0


def body(view):
    return [unit for unit in view.units if unit.kind == "paragraph"]


def test_cross_page_continuation_keeps_both_raw_blocks_and_hashes():
    with pymupdf.open() as document:
        page = document.new_page(width=600, height=800)
        page.insert_text((40, 90), "1 Methods", fontsize=15, fontname="hebo")
        textbox(
            page,
            40,
            640,
            "We measured the effects using repeated samples and carefully controlled environmental",
        )
        page.insert_text((290, 780), "1", fontsize=9)
        page = document.new_page(width=600, height=800)
        page.insert_text((290, 780), "2", fontsize=9)
        textbox(
            page,
            40,
            65,
            "conditions that were held constant for each repetition. "
            "The full protocol remains available in the source document.",
        )
        engine, paper, revision = store(document)
    with Session(engine) as session, session.begin():
        view = build_reading_document(session, paper, revision)
        paragraphs = body(view)
        assert len(paragraphs) == 1
        joined = paragraphs[0]
        assert joined.page_start == 1 and joined.page_end == 2
        assert joined.join_reason == "cross_page_continuation"
        assert len(joined.sources) == 2
        assert "that were held constant" in joined.text
        for source in joined.sources:
            chunk = session.get(Chunk, source.chunk_id)
            assert chunk.text[source.start_offset : source.end_offset] == source.text
            assert source.text_hash == text_hash(source.text)
            assert source.span_ids
        assert len([u for u in view.units if u.material_type == "running"]) == 2


def test_terminal_and_new_heading_do_not_join_unrelated_paragraphs():
    with pymupdf.open() as document:
        page = document.new_page(width=600, height=800)
        page.insert_text((40, 90), "1 Methods", fontsize=15, fontname="hebo")
        textbox(
            page, 40, 650, "The first paragraph ends here. Its samples were carefully controlled."
        )
        page = document.new_page(width=600, height=800)
        textbox(
            page, 40, 60, "and this is still a separate paragraph despite the lowercase opening."
        )
        page.insert_text((40, 260), "2 Results", fontsize=15, fontname="hebo")
        textbox(page, 40, 290, "the result belongs to a different section and cannot be joined.")
        engine, paper, revision = store(document)
    with Session(engine) as session, session.begin():
        view = build_reading_document(session, paper, revision)
        assert len(body(view)) == 3
        assert all(item.join_reason is None for item in body(view))
        assert any(unit.kind == "heading" and unit.text == "2 Results" for unit in view.units)


@pytest.mark.parametrize("graphic", [False, True])
def test_sparse_or_graphically_interrupted_pages_do_not_infer_continuity(graphic):
    with pymupdf.open() as document:
        page = document.new_page(width=600, height=800)
        textbox(
            page,
            40,
            640 if graphic else 280,
            "We measured the effects using repeated samples and carefully controlled environmental",
        )
        if graphic:
            # A nontext figure below the final prose interrupts the flow, even
            # though the next page starts with a plausible lowercase token.
            page.draw_rect((40, 710, 270, 770))
        page = document.new_page(width=600, height=800)
        textbox(
            page,
            40,
            65,
            "conditions that were reported independently in another part of the study.",
        )
        engine, paper, revision = store(document)
    with Session(engine) as session, session.begin():
        view = build_reading_document(session, paper, revision)
        assert len(body(view)) == 2
        assert all(unit.join_reason is None for unit in body(view))


def test_two_column_order_uses_layout_not_chunk_or_uuid_order():
    with pymupdf.open() as document:
        page = document.new_page(width=600, height=800)
        textbox(page, 40, 100, "Left first paragraph reports the main experimental setup.")
        textbox(page, 330, 100, "Right first paragraph follows the entire left column.")
        textbox(page, 40, 250, "Left second paragraph ends this column with a complete sentence.")
        textbox(page, 330, 250, "Right second paragraph finishes the reported results.")
        engine, paper, revision = store(document)
    with Session(engine) as session, session.begin():
        view = build_reading_document(session, paper, revision)
        assert [p.text.split()[0:2] for p in body(view)] == [
            ["Left", "first"],
            ["Left", "second"],
            ["Right", "first"],
            ["Right", "second"],
        ]


def test_right_column_continues_to_left_column_on_next_page():
    with pymupdf.open() as document:
        page = document.new_page(width=600, height=800)
        textbox(page, 40, 100, "Left first paragraph is read before right column content.")
        textbox(page, 40, 260, "Left second paragraph remains a separate completed paragraph.")
        textbox(page, 330, 100, "Right first paragraph precedes the page's final fragment.")
        textbox(
            page,
            330,
            640,
            "We measured the effects using repeated samples and carefully controlled environmental",
        )
        page = document.new_page(width=600, height=800)
        textbox(
            page,
            40,
            65,
            "conditions that were held constant throughout the reported protocol.",
        )
        textbox(page, 40, 270, "A second left paragraph completes the local reading sequence.")
        textbox(page, 330, 65, "The next right column follows both left paragraphs.")
        textbox(page, 330, 270, "The last right paragraph closes the source reading sequence.")
        engine, paper, revision = store(document)
    with Session(engine) as session, session.begin():
        view = build_reading_document(session, paper, revision)
        joined = [unit for unit in body(view) if unit.join_reason == "cross_page_continuation"]
        assert len(joined) == 1
        assert joined[0].page_start == 1 and joined[0].page_end == 2
        assert len(joined[0].sources) == 2
        assert "environmental conditions" in joined[0].text


def test_adjacent_continuation_joins_without_rewriting_raw_text():
    with pymupdf.open() as document:
        page = document.new_page(width=600, height=800)
        textbox(
            page,
            40,
            100,
            "The protocol used a carefully controlled\ncomparison and required repeated data",
        )
        # Separate raw blocks with a gap smaller than an ordinary paragraph gap.
        textbox(page, 40, 143, "were conducted under identical conditions.")
        engine, paper, revision = store(document)
    with Session(engine) as session, session.begin():
        original = [(c.id, c.text, c.bbox) for c in session.scalars(select(Chunk))]
        view = build_reading_document(session, paper, revision)
        assert len(body(view)) == 1
        assert len(body(view)[0].sources) == 2
        assert body(view)[0].join_reason == "adjacent_block_continuation"
        assert [(c.id, c.text, c.bbox) for c in session.scalars(select(Chunk))] == original


def test_figures_captions_labels_tables_fold_and_real_short_prose_remains():
    with pymupdf.open() as document:
        page = document.new_page(width=600, height=800)
        textbox(page, 40, 100, "We agree.")
        # A vector chart, a caption, an isolated numeric label and a legend label.
        page.draw_line((60, 240), (250, 240))
        page.draw_line((60, 240), (60, 170))
        page.draw_line((60, 240), (100, 215))
        page.draw_line((100, 215), (180, 190))
        page.insert_text((90, 205), "58.0", fontsize=9)
        page.insert_text((150, 225), "T3: Flights", fontsize=9)
        page.insert_text(
            (40, 275), "Figure 1. Synthetic chart, not scientific evidence.", fontsize=10
        )
        for x in (40, 180, 280):
            page.draw_line((x, 350), (x, 430))
        for y in (350, 390, 430):
            page.draw_line((40, y), (280, y))
        page.insert_text((50, 375), "Method", fontsize=10)
        page.insert_text((190, 375), "Value", fontsize=10)
        page.insert_text((50, 415), "Control", fontsize=10)
        page.insert_text((190, 415), "12.5", fontsize=10)
        engine, paper, revision = store(document)
    with Session(engine) as session, session.begin():
        view = build_reading_document(session, paper, revision)
        assert body(view)[0].text == "We agree."
        assert not any("58.0" in unit.text or "Flights" in unit.text for unit in body(view))
        materials = [unit for unit in view.units if unit.kind == "material"]
        assert {unit.material_type for unit in materials} >= {
            "figure",
            "caption",
            "figure_label",
            "table",
        }
        assert all(unit.reason and unit.solution for unit in materials)
        numeric = next(unit for unit in materials if unit.text == "58.0")
        assert numeric.confidence == "suspected" and numeric.sources[0].text == "58.0\n"
        assert any(
            unit.material_type == "figure" and unit.regions and not unit.sources
            for unit in materials
        )


def test_narrative_figure_references_and_equations_remain_body():
    with pymupdf.open() as document:
        page = document.new_page(width=600, height=800)
        textbox(
            page,
            40,
            110,
            "Figure 1 shows that the measured values vary with temperature. "
            "We discuss this dependence below.",
        )
        textbox(page, 40, 300, "Table 2 reports the observed values and the stated limitations.")
        page.insert_text((40, 500), "x = y + 2", fontsize=11)
        engine, paper, revision = store(document)
    with Session(engine) as session, session.begin():
        view = build_reading_document(session, paper, revision)
        assert len(body(view)) == 3
        assert any(unit.text.startswith("Figure 1 shows") for unit in body(view))
        assert any(unit.text.startswith("Table 2 reports") for unit in body(view))
        assert any(unit.text == "x = y + 2" for unit in body(view))
        assert not any(unit.material_type == "caption" for unit in view.units)


def test_mixed_heading_block_splits_title_from_body_at_exact_offsets():
    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text((45, 90), "1 Methods", fontsize=13, fontname="hebo")
        page.insert_text(
            (45, 106), "This body text belongs to the section and remains original.", fontsize=11
        )
        engine, paper, revision = store(document)
    with Session(engine) as session, session.begin():
        view = build_reading_document(session, paper, revision)
        title = next(unit for unit in view.units if unit.kind == "heading")
        paragraph = body(view)[0]
        assert title.text == "1 Methods"
        assert paragraph.text.startswith("This body text")
        if title.sources[0].chunk_id == paragraph.sources[0].chunk_id:
            assert title.sources[0].end_offset == paragraph.sources[0].start_offset


def test_explicit_refresh_enriches_legacy_parse_and_preserves_all_source_rows(tmp_path):
    with pymupdf.open() as document:
        page = document.new_page(width=600, height=800)
        textbox(page, 40, 100, "The local text is already indexed without any model calls.")
        pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 30, 30), False)
        pixmap.clear_with(170)
        page.insert_image((40, 250, 280, 450), pixmap=pixmap)
        engine, paper, revision = store(document, tmp_path, legacy=True)
    with Session(engine) as session, session.begin():
        original = {
            model.__tablename__: [
                (
                    row.id,
                    deepcopy(
                        {
                            column.name: getattr(row, column.name)
                            for column in model.__table__.columns
                        }
                    ),
                )
                for row in session.scalars(select(model))
            ]
            for model in (Chunk, Section, EvidenceSpan, DocumentParse)
        }
        before = build_reading_document(session, paper, revision)
        assert not any(unit.material_type == "figure" for unit in before.units)
        refreshed = build_reading_document(session, paper, revision, refresh=True)
        assert any(unit.material_type == "figure" for unit in refreshed.units)
        assert refreshed.refreshed_at
        assert refreshed.projection_hash != before.projection_hash
        again = build_reading_document(session, paper, revision)
        assert again.projection_hash == refreshed.projection_hash
        for model in (Chunk, Section, EvidenceSpan, DocumentParse):
            assert [
                (
                    row.id,
                    {column.name: getattr(row, column.name) for column in model.__table__.columns},
                )
                for row in session.scalars(select(model))
            ] == original[model.__tablename__]
        assert (tmp_path / "anonymous.pdf").read_bytes().startswith(b"%PDF")


def test_changed_external_pdf_is_not_used_or_overwritten(tmp_path):
    with pymupdf.open() as document:
        page = document.new_page()
        textbox(
            page, 45, 110, "The retained source remains readable when the external file changes."
        )
        engine, paper, revision = store(document, tmp_path)
    path = tmp_path / "anonymous.pdf"
    path.write_bytes(b"%PDF-private-replacement")
    with Session(engine) as session, session.begin():
        view = build_reading_document(session, paper, revision, refresh=True)
        assert body(view)
        assert any("字节已变化" in warning for warning in view.warnings)
        assert path.read_bytes() == b"%PDF-private-replacement"


def test_scanned_image_only_page_has_material_and_ocr_warning():
    with pymupdf.open() as document:
        page = document.new_page(width=600, height=800)
        pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 30, 30), False)
        pixmap.clear_with(170)
        page.insert_image((0, 0, 600, 800), pixmap=pixmap)
        engine, paper, revision = store(document)
    with Session(engine) as session, session.begin():
        view = build_reading_document(session, paper, revision)
        assert not body(view)
        assert any(unit.material_type == "figure" for unit in view.units)
        assert any("OCR" in warning for warning in view.warnings)


@pytest.mark.parametrize("target", ["chunk", "span", "artifact"])
def test_each_read_revalidates_raw_sources_and_cannot_reuse_corrupt_projection(target):
    with pymupdf.open() as document:
        textbox(
            document.new_page(), 45, 100, "A reliable original paragraph retains its source hash."
        )
        engine, paper, revision = store(document)
    with Session(engine) as session, session.begin():
        build_reading_document(session, paper, revision)
        if target == "chunk":
            row = session.scalar(select(Chunk))
            row.text += " altered"
        elif target == "span":
            row = session.scalar(select(EvidenceSpan))
            row.text_sha256 = "0" * 64
        else:
            row = session.scalar(select(DocumentParse))
            data = deepcopy(row.data)
            data["blocks"][0]["bbox"] = [0.0, 0.0, 1.0, 1.0]
            row.data = data
        session.flush()
        with pytest.raises(KnowledgeError):
            build_reading_document(session, paper, revision)
        assert len(list(session.scalars(select(ReadingDocumentProjection)))) == 1

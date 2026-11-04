"""Layout fixtures are synthetic and generated in memory; no private paper is required."""

import json

import pymupdf
from researchgraph.pdf_structure import parse_structure


def paragraph(page, x, y, text, width=490, size=11):
    assert page.insert_textbox((x, y, x + width, y + 95), text, fontsize=size) >= 0


def heading(page, y, text, size=15):
    page.insert_text((45, y), text, fontsize=size, fontname="hebo")


def table(page, xs, ys, values):
    for x in xs:
        page.draw_line((x, ys[0]), (x, ys[-1]))
    for y in ys:
        page.draw_line((xs[0], y), (xs[-1], y))
    for row, cells in enumerate(values):
        for col, text in enumerate(cells):
            page.insert_text((xs[col] + 7, ys[row] + 19), text, fontsize=10)


def by_text(structure, value):
    return next(b for b in structure["blocks"] if value in b["text"])


def test_cross_page_hierarchy_preserves_raw_text_and_explicit_intervals():
    with pymupdf.open() as document:
        first = document.new_page()
        heading(first, 90, "1 Methods")
        paragraph(
            first, 45, 115, "The protocol uses a controlled comparison of reported outcomes. " * 4
        )
        heading(first, 265, "1.1 Experimental design", size=13)
        paragraph(first, 45, 290, "The first part of the experiment specifies a fixed sample. " * 4)
        second = document.new_page()
        paragraph(
            second, 45, 90, "The experiment continues on the next page without a new heading. " * 4
        )
        heading(second, 265, "2 Results")
        paragraph(
            second, 45, 290, "The measured effect was 12.5 mg under the stated conditions. " * 4
        )
        expected = {
            f"p{page.number}:b{index}": (raw[4], list(raw[:4]))
            for page in document
            for index, raw in enumerate(
                b for b in page.get_text("blocks", sort=True) if b[6] == 0 and b[4].strip()
            )
        }
        result = parse_structure(document)
    method = next(s for s in result["sections"] if s["title"] == "1 Methods")
    design = next(s for s in result["sections"] if s["title"] == "1.1 Experimental design")
    assert design["parent_id"] == method["id"]
    assert design["end_page"] == method["end_page"] == 1
    continuation = by_text(result, "continues on the next page")
    assert continuation["section_ref"] == design["id"]
    assert len(result["sections"]) == 4
    assert {b["ref"]: (b["text"], b["bbox"]) for b in result["blocks"]} == expected
    assert all(b["lines"][0]["spans"][0]["font"] for b in result["blocks"])
    assert json.loads(json.dumps(result))["schema_version"] == "pdf-structure-1"


def test_references_are_excluded_until_appendix_without_deleting_source():
    with pymupdf.open() as document:
        page = document.new_page()
        heading(page, 90, "4 Discussion")
        paragraph(page, 45, 115, "These conclusions depend on the observed experiment. " * 4)
        heading(page, 265, "References")
        paragraph(
            page,
            45,
            290,
            "1. Smith J. A report about methods. 2022.\n2. Jones A. Another paper. 2023.",
        )
        heading(page, 430, "Appendix A Supplementary protocol")
        paragraph(
            page, 45, 455, "The supplementary protocol provides additional source details. " * 4
        )
        result = parse_structure(document)
    assert not by_text(result, "These conclusions")["excluded"]
    assert by_text(result, "Smith J.")["excluded"]
    assert by_text(result, "References")["excluded"]
    assert not by_text(result, "supplementary protocol provides")["excluded"]
    assert next(s for s in result["sections"] if s["role"] == "references")["excluded"]


def test_two_columns_read_left_then_right_and_respect_spanning_material():
    with pymupdf.open() as document:
        page = document.new_page(width=600, height=800)
        paragraph(
            page, 40, 100, "Left first paragraph explains the experimental protocol.", width=230
        )
        paragraph(
            page, 330, 100, "Right first paragraph follows the complete left column.", width=230
        )
        paragraph(page, 40, 220, "Left second paragraph completes the left column.", width=230)
        paragraph(page, 330, 220, "Right second paragraph completes the right column.", width=230)
        page.insert_text(
            (40, 370), "2 Results and a full-width section title across both columns", fontsize=16
        )
        paragraph(
            page,
            40,
            420,
            "Lower left paragraph contains all reported observations in the next section.",
            width=230,
        )
        paragraph(
            page,
            330,
            420,
            "Lower right paragraph ends the next section and retains the source details.",
            width=230,
        )
        result = parse_structure(document)
    ordered = [b["text"].strip().split("\n")[0] for b in result["blocks"]]
    assert ordered[0].startswith("Left first")
    assert ordered[1].startswith("Left second")
    assert ordered[2].startswith("Right first")
    assert ordered[3].startswith("Right second")
    assert ordered[4].startswith("2 Results")
    assert ordered[5].startswith("Lower left")
    assert ordered[6].startswith("Lower right")


def test_detected_table_preserves_headers_cells_values_and_source_positions():
    with pymupdf.open() as document:
        page = document.new_page()
        heading(page, 90, "3 Results")
        table(
            page,
            [45, 210, 365, 535],
            [130, 170, 210, 250],
            [
                ["Method", "Accuracy (%)", "Dose (mg)"],
                ["Control", "72.5", "2.0"],
                ["Treatment", "81.3", "3.0"],
            ],
        )
        result = parse_structure(document)
    assert len(result["tables"]) == 1
    found = result["tables"][0]
    assert found["rows"] == [
        ["Method", "Accuracy (%)", "Dose (mg)"],
        ["Control", "72.5", "2.0"],
        ["Treatment", "81.3", "3.0"],
    ]
    assert found["header"]["names"] == ["Method", "Accuracy (%)", "Dose (mg)"]
    value = next(c for c in found["cells"] if c["row"] == 2 and c["column"] == 1)
    assert value["text"] == "81.3"
    assert value["row_span"] == value["col_span"] == 1
    assert value["bbox"] == [210.0, 210.0, 365.0, 250.0]
    assert value["block_refs"] and found["block_refs"]
    assert found["section_ref"] == by_text(result, "3 Results")["section_ref"]
    assert not found["excluded"]


def test_merged_table_cell_keeps_col_span_and_does_not_invent_missing_value():
    with pymupdf.open() as document:
        page = document.new_page()
        for x in (45, 535):
            page.draw_line((x, 130), (x, 250))
        for y in (130, 170, 210, 250):
            page.draw_line((45, y), (535, y))
        page.draw_line((290, 170), (290, 250))
        page.insert_text((55, 155), "Reported measurements", fontsize=11)
        page.insert_text((55, 195), "Control", fontsize=11)
        page.insert_text((300, 195), "72.5", fontsize=11)
        page.insert_text((55, 235), "Treatment", fontsize=11)
        page.insert_text((300, 235), "81.3", fontsize=11)
        result = parse_structure(document)
    found = result["tables"][0]
    merged = next(c for c in found["cells"] if c["text"] == "Reported measurements")
    assert merged["col_span"] == 2
    assert found["rows"][0] == ["Reported measurements", ""]


def test_repeated_headers_footers_are_retained_but_excluded():
    with pymupdf.open() as document:
        for number in range(2):
            page = document.new_page()
            page.insert_text((45, 30), "Journal of Synthetic Testing", fontsize=9)
            if number == 0:
                heading(page, 100, "1 Methods")
            paragraph(
                page, 45, 150, "This body text belongs to the same section across pages. " * 5
            )
            page.insert_text((290, 815), str(number + 1), fontsize=9)
        result = parse_structure(document)
    running = [b for b in result["blocks"] if "Journal" in b["text"]]
    assert len(running) == 2 and all(b["excluded"] and b["kind"] == "header" for b in running)
    assert all(b["excluded"] for b in result["blocks"] if b["text"].strip() in {"1", "2"})
    assert len(result["sections"]) == 2


def test_blank_scanned_page_warns_without_inventing_text_or_chapters():
    with pymupdf.open() as document:
        document.new_page()
        document.new_page()
        result = parse_structure(document)
    assert result["blocks"] == result["tables"] == []
    assert len(result["sections"]) == 1
    assert len([warning for warning in result["warnings"] if "OCR" in warning]) == 2


def test_pdf_bookmarks_support_nonstandard_section_titles():
    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text((45, 90), "An unusual section name", fontsize=11)
        paragraph(
            page, 45, 120, "The source text uses a bookmark instead of distinctive typography. " * 5
        )
        document.set_toc([[1, "An unusual section name", 1]])
        result = parse_structure(document)
    section = next(s for s in result["sections"] if s["title"] == "An unusual section name")
    assert by_text(result, "The source text")["section_ref"] == section["id"]


def test_unheaded_pages_and_quantities_do_not_create_per_page_sections():
    with pymupdf.open() as document:
        for _ in range(2):
            page = document.new_page()
            paragraph(page, 45, 130, "A continuing paragraph without section headings. " * 6)
            page.insert_text((45, 290), "12.5 mg", fontsize=11)
        result = parse_structure(document)
    assert len(result["sections"]) == 1
    assert all(b["section_ref"] == "s0" for b in result["blocks"])


def test_reference_section_continues_across_pages_without_false_citation_headings():
    with pymupdf.open() as document:
        page = document.new_page()
        heading(page, 90, "References")
        paragraph(page, 45, 120, "1. Smith A. A first synthetic reference. 2021.")
        page = document.new_page()
        page.insert_text((45, 120), "2. Synthetic journal article", fontsize=11, fontname="hebo")
        paragraph(
            page, 45, 170, "A reference continuation with authors, publication and year 2022."
        )
        result = parse_structure(document)
    assert all(b["excluded"] for b in result["blocks"])
    assert by_text(result, "reference continuation")["section_ref"] != "s0"


def test_table_detector_failure_preserves_source_and_reports_warning(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("synthetic table detector failure")

    monkeypatch.setattr(pymupdf.Page, "find_tables", fail)
    with pymupdf.open() as document:
        page = document.new_page()
        paragraph(page, 45, 120, "The original text remains available when table detection fails.")
        result = parse_structure(document)
    assert result["tables"] == []
    assert "original text remains" in result["blocks"][0]["text"]
    assert any("表格结构解析失败" in warning for warning in result["warnings"])


def test_unnumbered_heading_font_hierarchy_is_preserved():
    with pymupdf.open() as document:
        page = document.new_page()
        heading(page, 170, "Study Design", size=16)
        paragraph(
            page, 45, 200, "A consistent body font provides the baseline for heading levels. " * 5
        )
        heading(page, 330, "Participants", size=13)
        paragraph(
            page, 45, 360, "The participants are described with source details and conditions. " * 5
        )
        heading(page, 500, "Observed Outcomes", size=16)
        result = parse_structure(document)
    study = next(s for s in result["sections"] if s["title"] == "Study Design")
    participants = next(s for s in result["sections"] if s["title"] == "Participants")
    outcomes = next(s for s in result["sections"] if s["title"] == "Observed Outcomes")
    assert participants["parent_id"] == study["id"] and participants["level"] == 2
    assert outcomes["parent_id"] == "s0" and outcomes["level"] == study["level"] == 1


def test_heading_and_references_merged_with_body_keep_full_source_block():
    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text((45, 90), "Methods", fontsize=12)
        paragraph(page, 45, 94, "A synthetic method is described across several lines. " * 8)
        page.insert_text((45, 360), "References", fontsize=12)
        # More small-font reference text than main text must not redefine the
        # main body size or cause plain source sentences to become headings.
        assert (
            page.insert_textbox(
                (45, 364, 535, 720),
                "Smith A. A synthetic source record from 2022. " * 90,
                fontsize=7,
            )
            >= 0
        )
        original = [b[4] for b in page.get_text("blocks", sort=True) if b[6] == 0]
        result = parse_structure(document)
    assert len(original[0]) > 180 and original[0].startswith("Methods\n")
    assert original[1].startswith("References\n")
    assert [s["title"] for s in result["sections"]] == ["Document", "Methods", "References"]
    assert [b["text"] for b in result["blocks"]] == original
    assert result["blocks"][0]["heading_text"] == "Methods"
    assert not result["blocks"][0]["excluded"] and result["blocks"][1]["excluded"]


def test_inline_large_symbol_partial_bold_and_plain_number_do_not_create_sections():
    with pymupdf.open() as document:
        page = document.new_page()
        heading(page, 90, "1 Methods")
        paragraph(page, 45, 120, "A stable body font describes the source procedure. " * 5)
        page.insert_text((45, 265), "Measured condition ", fontsize=11)
        x = 45 + pymupdf.get_text_length("Measured condition ", fontsize=11)
        page.insert_text((x, 265), "x", fontsize=18)
        page.insert_text((x + 12, 265), " remains stable", fontsize=11)
        bold = "Strong inline terminology "
        page.insert_text((45, 310), bold, fontsize=11, fontname="hebo")
        x = 45 + pymupdf.get_text_length(bold, fontsize=11, fontname="hebo")
        page.insert_text((x, 310), "matters", fontsize=11)
        page.insert_text((45, 350), "2 A short ordinary observation", fontsize=11)
        # A bold detached outline/list number is not a complete heading.
        page.insert_text((45, 390), "3.2.1", fontsize=11, fontname="hebo")
        page.insert_text((80, 390), "This is ordinary source prose", fontsize=11)
        result = parse_structure(document)
    assert [s["title"] for s in result["sections"]] == ["Document", "1 Methods"]


def test_a_heading_outside_grid_is_retained_when_shared_block_overlaps_table(monkeypatch):
    from researchgraph import pdf_structure

    def synthetic_table(page, blocks, warnings):
        for block in blocks:
            block["kind"] = "table"
            # Mimic a detected grid overlapping only the lower lines of a
            # merged block; the Methods line itself is outside the grid.
            block["table_regions"] = [[45.0, 110.0, 535.0, 200.0]]
        return []

    monkeypatch.setattr(pdf_structure, "_tables", synthetic_table)
    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text((45, 90), "Methods", fontsize=12)
        paragraph(page, 45, 94, "A source paragraph can overlap the inferred table region. " * 5)
        result = parse_structure(document)
    assert [s["title"] for s in result["sections"]] == ["Document", "Methods"]
    assert result["blocks"][0]["heading_text"] == "Methods"

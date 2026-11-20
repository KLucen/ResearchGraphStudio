import pytest
from pydantic import ValidationError
from researchgraph.model_document_contracts import ModelDocumentParseInput


def segment(kind: str, **kwargs: object) -> dict[str, object]:
    return {
        "chapter_ref": "ch-1",
        "chapter_title": "Introduction",
        "chapter_level": 1,
        "chapter_order": 0,
        "kind": kind,
        "ordinal": 0,
        **kwargs,
    }


def test_model_document_accepts_text_formula_and_table() -> None:
    payload = ModelDocumentParseInput(
        parse_version="model-document.v1",
        modality="pdf",
        segments=[
            segment("paragraph", text="A paragraph."),
            segment("formula", text="a / b", latex=r"\\frac{a}{b}", ordinal=1),
            segment(
                "table",
                raw_table_text="A | B\n1 | 2",
                table_data={"columns": ["A", "B"], "rows": [["1", "2"]]},
                ordinal=2,
            ),
        ],
    )
    assert len(payload.segments) == 3
    assert payload.segments[1].latex is not None


def test_model_document_rejects_empty_formula_and_table() -> None:
    for kind in ("formula", "table"):
        try:
            ModelDocumentParseInput(
                parse_version="model-document.v1",
                segments=[segment(kind)],
            )
        except ValidationError:
            pass
        else:
            raise AssertionError(f"{kind} without material should be rejected")


def test_model_document_rejects_out_of_order_segments() -> None:
    try:
        ModelDocumentParseInput(
            parse_version="model-document.v1",
            segments=[
                segment("paragraph", text="second", ordinal=2),
                segment("paragraph", text="first", ordinal=1),
            ],
        )
    except ValidationError as exc:
        assert "章节顺序" in str(exc)
    else:
        raise AssertionError("out-of-order model output should be rejected")


@pytest.mark.parametrize("second_kind", ["paragraph", "formula", "table"])
def test_one_chapter_cannot_publish_two_materials_at_the_same_ordinal(second_kind):
    with pytest.raises(ValidationError, match="duplicate_segment_ordinal"):
        ModelDocumentParseInput.model_validate(
            {
                "parse_version": "test-1",
                "segments": [
                    segment("paragraph", text="First material."),
                    segment(second_kind, text="Second material."),
                ],
            }
        )


def test_distinct_chapters_keep_independent_ordinal_sequences():
    result = ModelDocumentParseInput.model_validate(
        {
            "parse_version": "test-1",
            "segments": [
                segment("paragraph", text="First chapter."),
                segment(
                    "paragraph",
                    text="Second chapter.",
                    chapter_ref="ch-2",
                    chapter_title="Results",
                    chapter_order=1,
                ),
            ],
        }
    )
    assert [item.ordinal for item in result.segments] == [0, 0]


@pytest.mark.parametrize(
    "change",
    [
        {"chapter_order": "0"},
        {"chapter_level": True},
        {"ordinal": "0"},
        {"chapter_ref": "  "},
        {"chapter_title": "\n"},
        {"confidence": "0.5"},
        {"locator": {"page_start": "1", "page_end": 2}},
        {"locator": {"page_start": 2, "page_end": 1}},
        {"locator": {"page_start": 1}},
        {"locator": {"page_index": True}},
        {"locator": {"bbox": [0, 0, 3]}},
        {"locator": {"bbox": [10, 0, 3, 5]}},
        {"locator": {"bbox": [0, 0, float("inf"), 5]}},
        {"locator": {"source_parts": [{"page_start": 1}]}},
        {"table_data": {"private": float("nan")}},
        {"table_data": {"private": object()}},
    ],
)
def test_document_material_rejects_coerced_types_and_invalid_json_shapes(change):
    with pytest.raises(ValidationError):
        ModelDocumentParseInput.model_validate(
            {
                "parse_version": "test-1",
                "segments": [segment("paragraph", text="Source.", **change)],
            }
        )


@pytest.mark.parametrize(
    "change",
    [
        {"chapter_title": "Different"},
        {"chapter_level": 2},
        {"chapter_order": 1},
        {"chapter_ref": "another-chapter"},
    ],
)
def test_one_chapter_identity_cannot_silently_point_to_different_sections(change):
    with pytest.raises(ValidationError, match="chapter_.*_conflict"):
        ModelDocumentParseInput.model_validate(
            {
                "parse_version": "test-1",
                "segments": [
                    segment("paragraph", text="First."),
                    segment("paragraph", text="Second.", ordinal=1, **change),
                ],
            }
        )


def test_valid_locator_preserves_original_pages_and_coordinates_without_normalization():
    locator = {
        "page_start": 2,
        "page_end": 3,
        "page_index": 1,
        "bbox_list": [[10, 20, 50, 60.5]],
        "source_parts": [{"page_start": 2, "page_end": 2}, {"page_start": 3, "page_end": 3}],
        "source_mode": "model_batch",
    }
    result = ModelDocumentParseInput.model_validate(
        {
            "parse_version": "test-1",
            "segments": [segment("paragraph", text="Source.", locator=locator)],
        }
    )
    assert result.segments[0].locator == locator

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

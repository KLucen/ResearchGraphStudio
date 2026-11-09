from pathlib import Path
import importlib.util
import json
import sys

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("lite_contracts_examples", root / "schemas" / "contracts.py")
contracts = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = contracts
spec.loader.exec_module(contracts)


def load(name):
    return json.loads((root / "examples" / name).read_text(encoding="utf-8"))


def test_card_example_validates():
    output = contracts.PaperCardDraft.model_validate(load("paper_card_fictional.json"))
    contracts.validate_references(output, {"sp-1", "sp-2", "sp-3"})


def test_guide_example_validates():
    output = contracts.ReadingGuideDraft.model_validate(load("reading_guide_fictional.json"))
    contracts.validate_references(output, {"sp-2"}, requested_section_id="sec-03")


def test_qa_example_validates():
    output = contracts.QAAnswerDraft.model_validate(load("qa_answer_fictional.json"))
    contracts.validate_references(output, {"sp-2"})


def test_json_schemas_parse():
    for p in (root / "schemas" / "generated").glob("*.json"):
        content = json.loads(p.read_text(encoding="utf-8"))
        assert content.get("type") == "object" and "properties" in content

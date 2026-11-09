import json
import tempfile
from pathlib import Path

from researchgraph.app import create_app

root = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix="researchgraph-contracts-") as directory:
    schema = create_app(Path(directory), "schema-only-" * 4).openapi()
(root / "packages/contracts/openapi.json").write_text(
    json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)

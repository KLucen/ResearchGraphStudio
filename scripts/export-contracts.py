import json
from pathlib import Path

from researchgraph.app import create_app

root = Path(__file__).resolve().parents[1]
schema = create_app(root / ".local" / "unused-contract-export", "schema-only-" * 4).openapi()
(root / "packages/contracts/openapi.json").write_text(
    json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)

"""Prepare the pinned offline formula model for a Windows/source build.

Only this explicit developer command downloads weights. Installed applications
never contact Hugging Face or download a model on startup or during recognition.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import urllib.request
from pathlib import Path


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def prepare(target: Path, *, download: bool = False) -> None:
    root = Path(__file__).resolve().parent.parent
    manifest_path = root / "resources" / "formula-model-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    target.mkdir(parents=True, exist_ok=True)
    total = 0
    assets = manifest.get("files")
    if not isinstance(assets, list):
        raise SystemExit("Invalid formula asset manifest: files must be a list")
    for asset in assets:
        if not isinstance(asset, dict):
            raise SystemExit("Invalid formula asset manifest entry")
        name = asset.get("name")
        expected = asset.get("sha256")
        if not isinstance(name, str) or not isinstance(expected, str):
            raise SystemExit("Invalid formula asset manifest entry")
        if Path(name).name != name:
            raise SystemExit("Invalid formula asset manifest path")
        path = target / name
        if path.is_file() and digest(path) == expected:
            total += path.stat().st_size
            continue
        if not download:
            raise SystemExit(f"Missing or invalid formula asset: {name}; run with --download")
        url = f"https://huggingface.co/{manifest['model_id']}/resolve/{manifest['revision']}/{name}"
        temporary = path.with_name(name + ".partial")
        print(f"Downloading pinned formula asset: {name}", flush=True)
        request = urllib.request.Request(url, headers={"User-Agent": "ResearchGraph-build/1"})
        with urllib.request.urlopen(request, timeout=60) as response, temporary.open("wb") as out:
            count = 0
            while block := response.read(1024 * 1024):
                count += len(block)
                if count > 150 * 1024 * 1024:
                    raise SystemExit("Formula asset exceeded the download limit")
                out.write(block)
        if digest(temporary) != expected:
            temporary.unlink()
            raise SystemExit(f"Formula asset SHA-256 mismatch: {name}")
        temporary.replace(path)
        total += path.stat().st_size
    shutil.copyfile(manifest_path, target / "manifest.json")
    print(f"Offline formula model verified: {len(manifest['files'])} assets / {total} bytes")


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, default=root / ".local" / "formula-model")
    parser.add_argument("--download", action="store_true", help="Download pinned missing assets")
    args = parser.parse_args()
    prepare(args.target.resolve(), download=args.download)


if __name__ == "__main__":
    main()

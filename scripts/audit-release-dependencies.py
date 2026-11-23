"""Scan installed Python, production desktop and Windows Rust dependencies before release."""

import argparse
import json
import re
import tomllib
from collections.abc import Iterator
from importlib.metadata import distribution
from pathlib import Path
from urllib.request import Request, urlopen

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

Dependency = tuple[str, str, str]
ROOT = Path(__file__).resolve().parents[1]


def python_runtime() -> Iterator[Dependency]:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    pending = [Requirement(item) for item in project["dependencies"]]
    visited: set[str] = set()
    while pending:
        requirement = pending.pop()
        name = canonicalize_name(requirement.name)
        installed = distribution(name)
        if installed.version not in requirement.specifier:
            raise ValueError(f"{name} {installed.version} does not satisfy {requirement.specifier}")
        if name in visited:
            continue
        visited.add(name)
        yield "PyPI", name, installed.version
        for dependency in installed.requires or []:
            item = Requirement(dependency)
            if item.marker is None or item.marker.evaluate({"extra": ""}):
                pending.append(item)


def npm_runtime(node: dict[str, object]) -> Iterator[Dependency]:
    for field in ("dependencies", "optionalDependencies"):
        children = node.get(field)
        if not isinstance(children, dict):
            continue
        for name, item in children.items():
            if not isinstance(item, dict):
                continue
            version = item.get("version")
            if isinstance(version, str) and re.fullmatch(r"[0-9][\w.+-]*", version):
                yield "npm", str(item.get("from", name)), version
            yield from npm_runtime(item)


def rust_runtime(tree: str) -> Iterator[Dependency]:
    for line in tree.splitlines():
        match = re.match(r"^([\w-]+) v([\w.+-]+)(?:\s+\(\*\))?$", line)
        if match:
            yield "crates.io", match[1], match[2]


def advisories(dependencies: list[Dependency]) -> list[dict[str, object]]:
    hits = []
    for start in range(0, len(dependencies), 100):
        page = dependencies[start : start + 100]
        queries = [
            {"version": version, "package": {"name": name, "ecosystem": ecosystem}}
            for ecosystem, name, version in page
        ]
        request = Request(
            "https://api.osv.dev/v1/querybatch",
            data=json.dumps({"queries": queries}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request, timeout=30) as response:
            results = json.load(response)["results"]
        for (ecosystem, name, version), result in zip(page, results, strict=True):
            if result.get("vulns"):
                hits.append(
                    {
                        "ecosystem": ecosystem,
                        "name": name,
                        "version": version,
                        "advisories": [record["id"] for record in result["vulns"]],
                    }
                )
    return hits


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--npm-tree", required=True, type=Path)
    parser.add_argument("--cargo-tree", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    npm = set(
        dependency
        for root in json.loads(args.npm_tree.read_text(encoding="utf-8-sig"))
        for dependency in npm_runtime(root)
    )
    rust = set(rust_runtime(args.cargo_tree.read_text(encoding="utf-8-sig")))
    python = set(python_runtime())
    if not npm or not rust or not python:
        raise ValueError("All three runtime dependency inventories are required")
    dependencies = sorted(npm | rust | python)
    args.output.mkdir(parents=True, exist_ok=True)
    purl = {"npm": "npm", "PyPI": "pypi", "crates.io": "cargo"}
    components = [
        {
            "type": "library",
            "name": name,
            "version": version,
            "purl": f"pkg:{purl[ecosystem]}/{name.replace('@', '%40')}@{version}",
        }
        for ecosystem, name, version in dependencies
    ]
    (args.output / "windows-runtime-sbom.json").write_text(
        json.dumps(
            {
                "bomFormat": "CycloneDX",
                "specVersion": "1.6",
                "version": 1,
                "components": components,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    hits = advisories(dependencies)
    (args.output / "windows-runtime-advisories.json").write_text(
        json.dumps({"scanned": len(dependencies), "matches": hits}, indent=2), encoding="utf-8"
    )
    print(f"OSV checked {len(dependencies)} resolved runtime versions; {len(hits)} matches")
    return int(bool(hits))


if __name__ == "__main__":
    raise SystemExit(main())

"""Reject a hash lock that omits or contradicts a declared runtime dependency."""

import re
import tomllib
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    lock = (root / "requirements-win-64.lock").read_text(encoding="utf-8")
    versions = {
        canonicalize_name(name): version
        for name, version in re.findall(r"^([A-Za-z0-9_.-]+)==([^\s\\]+)", lock, re.M)
    }
    errors = []
    dependencies = project["project"]["dependencies"]
    for declared in dependencies:
        requirement = Requirement(declared)
        version = versions.get(canonicalize_name(requirement.name))
        if version is None or version not in requirement.specifier:
            errors.append(str(requirement))
    if errors:
        raise SystemExit(
            "Runtime dependencies absent/incompatible in Windows lock: " + ", ".join(errors)
        )
    print(f"Runtime dependency lock covers {len(dependencies)} declared requirements.")


if __name__ == "__main__":
    main()

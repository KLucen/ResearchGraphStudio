"""Scan candidate source content, even tracked ignored files; never print matching secrets."""

import argparse
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gitleaks", required=True, type=Path)
    parser.add_argument("--staged", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    command = (
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"]
        if args.staged
        else ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"]
    )
    names = set(subprocess.check_output(command, cwd=root).decode("utf-8").split("\0")) - {""}
    blocked = []
    with tempfile.TemporaryDirectory(prefix="rgs-source-scan-") as folder:
        boundary = Path(folder).resolve()
        count = 0
        for name in sorted(names):
            path = root / name
            normalized = name.lower()
            if not args.staged and not path.is_file():
                continue
            if (
                re.search(
                    r"(^|/)(\.local|data|private|secrets|credentials|logs|node_modules|target|binaries)/",
                    normalized,
                )
                or re.search(
                    r"\.(sqlite3?|db)(-wal|-shm)?$|\.(log|jsonl|pem|key|exe|msi|zip|epub|ris|bib)$",
                    normalized,
                )
                or (
                    Path(normalized).name.startswith(".env")
                    and Path(normalized).name != ".env.example"
                )
                or (normalized.endswith(".pdf") and not normalized.startswith("tests/fixtures/"))
                or (
                    not args.staged
                    and (path.is_symlink() or not path.resolve().is_relative_to(root))
                )
            ):
                blocked.append(name)
                continue
            target = (boundary / name).resolve()
            if not target.is_relative_to(boundary):
                raise SystemExit("Unsafe source path; scan refused")
            target.parent.mkdir(parents=True, exist_ok=True)
            if args.staged:
                target.write_bytes(subprocess.check_output(["git", "show", ":" + name], cwd=root))
            else:
                shutil.copyfile(path, target)
            count += 1
        if blocked:
            print("Private/runtime paths found; Commit/Push must stop:")
            print("\n".join(blocked))
            raise SystemExit(1)
        result = subprocess.run(
            [
                str(args.gitleaks.resolve()),
                "dir",
                str(boundary),
                "--redact=100",
                "--no-banner",
                "--exit-code",
                "1",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode:
            print("Gitleaks did not pass. Commit/Push must stop; inspect a redacted local report.")
            raise SystemExit(result.returncode)
        print(f"Source content scan passed: {count} files; private path rules and Gitleaks.")


if __name__ == "__main__":
    main()

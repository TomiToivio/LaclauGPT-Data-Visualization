"""Fail CI if tracked public files contain obvious private runtime material."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

FORBIDDEN_PATH_PARTS = {
    "data",
    "outputs",
    "exports",
    "reviews",
    "cache",
    ".streamlit",
}
FORBIDDEN_SUFFIXES = {".sqlite", ".sqlite3", ".db", ".duckdb", ".pem", ".key"}
SECRET_PATTERNS = [
    re.compile(r"mongodb(?:\+srv)?://[^\s/:]+:[^\s/@]+@", re.IGNORECASE),
    re.compile(r"redis://[^\s/:]+:[^\s/@]+@", re.IGNORECASE),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
]
TEXT_SUFFIXES = {
    ".py", ".md", ".toml", ".yml", ".yaml", ".json", ".txt", ".js", ".html", ".css", ".example"
}


def tracked_files() -> list[Path]:
    raw = subprocess.check_output(["git", "ls-files", "-z"])
    return [Path(item.decode()) for item in raw.split(b"\0") if item]


def main() -> int:
    violations: list[str] = []
    for path in tracked_files():
        parts = set(path.parts)
        if FORBIDDEN_PATH_PARTS.intersection(parts):
            violations.append(f"forbidden tracked runtime path: {path}")
            continue
        if path.suffix.lower() in FORBIDDEN_SUFFIXES:
            violations.append(f"forbidden tracked runtime/database file: {path}")
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in {"README.md", "AGENTS.md"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                violations.append(f"credential-like content in {path}")
                break
    if violations:
        print("Public-tree policy violations:")
        for violation in violations:
            print(f"- {violation}")
        return 1
    print("Public-tree policy check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

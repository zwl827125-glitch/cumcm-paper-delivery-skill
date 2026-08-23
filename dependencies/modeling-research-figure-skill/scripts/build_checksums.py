#!/usr/bin/env python3
"""Write deterministic SHA-256 checksums for distributable Skill files."""

from __future__ import annotations

import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "CHECKSUMS.sha256"
EXCLUDED_PARTS = {".git", "__pycache__", ".venv", "dist"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".zip"}


def included(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    if path == OUTPUT or any(part in EXCLUDED_PARTS for part in relative.parts):
        return False
    return path.suffix.casefold() not in EXCLUDED_SUFFIXES


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


files = sorted((path for path in ROOT.rglob("*") if path.is_file() and included(path)), key=lambda path: path.as_posix())
lines = [f"{digest(path)}  {path.relative_to(ROOT).as_posix()}" for path in files]
OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
print(f"Wrote {OUTPUT} with {len(lines)} entries.")

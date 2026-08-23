#!/usr/bin/env python3
"""Verify files listed in CHECKSUMS.sha256."""

from __future__ import annotations

import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "CHECKSUMS.sha256"
failures: list[str] = []

for line in MANIFEST.read_text(encoding="utf-8").splitlines():
    expected, relative = line.split("  ", 1)
    path = ROOT / Path(relative)
    if not path.is_file():
        failures.append(f"missing: {relative}")
        continue
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected:
        failures.append(f"changed: {relative}")

if failures:
    raise SystemExit("\n".join(failures))
print("All checksums match.")

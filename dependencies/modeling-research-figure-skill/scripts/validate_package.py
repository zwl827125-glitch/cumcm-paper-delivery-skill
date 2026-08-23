#!/usr/bin/env python3
"""Self-contained release validation for the figure-gallery Skill."""

from __future__ import annotations

import hashlib
import json
import re
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
frontmatter = re.match(r"^---\n(.*?)\n---", skill, re.DOTALL)
require(frontmatter is not None, "SKILL.md frontmatter is missing")
require("name: modeling-research-figure-skill" in frontmatter.group(1), "Skill name is inconsistent")
require("description:" in frontmatter.group(1), "Skill description is missing")
require("TODO" not in skill, "Unfinished TODO in SKILL.md")

catalog = json.loads((ROOT / "references" / "catalog.json").read_text(encoding="utf-8"))
references = json.loads((ROOT / "references" / "reference-assets.json").read_text(encoding="utf-8"))
upstream = json.loads((ROOT / "references" / "upstream-assets.json").read_text(encoding="utf-8"))
formal = catalog["items"]
auxiliary = references["items"]
require(len(formal) == 35, f"Expected 35 formal items, found {len(formal)}")
require(len(auxiliary) == 20, f"Expected 20 auxiliary items, found {len(auxiliary)}")
require(len({item["id"] for item in formal}) == 35, "Duplicate formal IDs")
require(len({item["id"] for item in auxiliary}) == 20, "Duplicate auxiliary IDs")
require(sum(item["status"] == "runnable" for item in formal) == 16, "Expected 16 runnable templates")
require(len(upstream["assets"]) == 15, "Expected 15 attributed upstream assets")
formal_ids = {item["id"] for item in formal}
source_ids = {item["id"] for item in auxiliary if item["status"] == "source-reference"}
for item in auxiliary:
    require(set(item.get("related_formal_ids", [])) <= formal_ids, f"Unknown formal mapping in {item['id']}")
    require(set(item.get("source_ids", [])) <= source_ids, f"Unknown source mapping in {item['id']}")

declared_paths: list[str] = []
for item in formal:
    declared_paths.extend(path for path in (item.get("preview"), item.get("vector"), item.get("generator")) if path)
for item in auxiliary:
    declared_paths.append(item["path"])
missing = sorted(path for path in declared_paths if not (ROOT / path).is_file())
require(not missing, f"Missing catalog paths: {missing}")

png_files = sorted((ROOT / "assets").rglob("*.png"))
svg_files = sorted((ROOT / "assets").rglob("*.svg"))
require(len(png_files) == 55, f"Expected 55 PNG assets, found {len(png_files)}")
require(len(svg_files) == 20, f"Expected 20 SVG assets, found {len(svg_files)}")
png_hashes = [hashlib.sha256(path.read_bytes()).hexdigest() for path in png_files]
require(len(set(png_hashes)) == 55, "PNG assets contain byte-identical duplicates")
for item in upstream["assets"]:
    path = ROOT / item["local"]
    require(path.is_file(), f"Missing upstream-derived asset: {item['local']}")
    require(hashlib.sha256(path.read_bytes()).hexdigest().upper() == item["sha256"], f"Upstream-derived asset changed: {item['local']}")

generated_svgs = list((ROOT / "assets" / "vectors" / "modeling-templates").glob("*.svg"))
require(len(generated_svgs) == 16, "Expected 16 generated SVG templates")
require(all("<text" in path.read_text(encoding="utf-8") for path in generated_svgs), "Generated SVG text is not editable")

class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.paths: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        for key in ("src", "href"):
            value = values.get(key)
            if value and not value.startswith(("#", "http:", "https:", "mailto:")):
                self.paths.append(value)


parser = LinkParser()
parser.feed((ROOT / "index.html").read_text(encoding="utf-8"))
broken_links = sorted({path for path in parser.paths if not (ROOT / path).exists()})
require(not broken_links, f"Broken local HTML links: {broken_links}")

forbidden = []
private_markers = (
    "C:" + "\\Users\\",
    "codex-" + "clipboard",
    "AppData" + "\\Local\\Temp",
)
for path in ROOT.rglob("*"):
    if not path.is_file() or path.suffix.casefold() in {".png", ".pyc"}:
        continue
    try:
        value = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        continue
    if any(marker.casefold() in value.casefold() for marker in private_markers):
        forbidden.append(str(path.relative_to(ROOT)))
require(not forbidden, f"Private local paths found in: {forbidden}")

pyc_files = list(ROOT.rglob("*.pyc"))
require(not pyc_files, f"Compiled Python files must not ship: {pyc_files}")
print("Package validation passed: 35 formal items, 20 auxiliary items, 55 unique PNG, 20 SVG.")

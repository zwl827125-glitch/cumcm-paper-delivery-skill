#!/usr/bin/env python3
"""Search the bundled formal figure catalog without third-party packages."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "references" / "catalog.json"


def normalized_tokens(value: str) -> list[str]:
    return [token for token in re.split(r"[^\w\u4e00-\u9fff]+", value.casefold()) if token]


def searchable_text(item: dict) -> str:
    values = [
        item.get("id", ""),
        item.get("title_zh", ""),
        item.get("title_en", ""),
        item.get("collection", ""),
        item.get("status", ""),
        *item.get("suitable_for", []),
        *item.get("roles", []),
        *item.get("tags", []),
    ]
    return " ".join(str(value) for value in values).casefold()


def score(item: dict, tokens: list[str]) -> int:
    haystack = searchable_text(item)
    if not tokens:
        return 1
    if not all(token in haystack for token in tokens):
        return 0
    item_id = item.get("id", "").casefold()
    titles = f"{item.get('title_zh', '')} {item.get('title_en', '')}".casefold()
    tags = " ".join(item.get("tags", [])).casefold()
    total = 10
    for token in tokens:
        total += 8 if token in item_id else 0
        total += 5 if token in titles else 0
        total += 3 if token in tags else 0
    return total


def main() -> None:
    parser = argparse.ArgumentParser(description="Search the modeling and research figure gallery.")
    parser.add_argument("query", nargs="?", default="", help="Words such as sensitivity, optimization, 热图, or imaging")
    parser.add_argument("--collection", help="Filter by collection")
    parser.add_argument("--status", choices=["runnable", "static-reference"], help="Filter by execution status")
    parser.add_argument("--limit", type=int, default=8, help="Maximum results")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of a table")
    args = parser.parse_args()

    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    tokens = normalized_tokens(args.query)
    matches = []
    for item in catalog["items"]:
        if args.collection and item.get("collection") != args.collection:
            continue
        if args.status and item.get("status") != args.status:
            continue
        item_score = score(item, tokens)
        if item_score:
            matches.append((item_score, item))
    matches.sort(key=lambda pair: (-pair[0], pair[1]["id"]))
    items = [item for _, item in matches[: max(args.limit, 0)]]

    if args.json:
        print(json.dumps(items, ensure_ascii=False, indent=2))
        return

    if not items:
        print("No matching figures.")
        return

    for item in items:
        generator = item.get("generator") or "static reference"
        print(f"{item['id']}\n  {item['title_zh']} / {item['title_en']}\n  {item['status']} | {item['preview']}\n  {generator}")


if __name__ == "__main__":
    main()

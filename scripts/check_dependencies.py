from __future__ import annotations

import json
import re
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
MANIFEST = SKILL_DIR / "references" / "dependency-manifest.json"


def discover_skill_names() -> dict[str, str]:
    roots = [Path.home() / ".codex" / "skills", Path.home() / ".codex" / "plugins"]
    found: dict[str, str] = {}
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("SKILL.md"):
            try:
                head = path.read_text(encoding="utf-8", errors="strict")[:4096]
            except (OSError, UnicodeError):
                continue
            match = re.search(r"(?m)^name:\s*[\"']?([^\"'\r\n]+)", head)
            if match:
                name = match.group(1).strip()
                found.setdefault(name, str(path))
                parts = list(path.parts)
                if "cache" in parts:
                    cache_index = parts.index("cache")
                    if len(parts) > cache_index + 2:
                        plugin_name = parts[cache_index + 2]
                        found.setdefault(f"{plugin_name}:{name}", str(path))
    return found


def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    found = discover_skill_names()
    groups = {}
    for group in ("required", "recommended", "conditional"):
        groups[group] = {
            name: {"installed": name in found, "path": found.get(name)}
            for name in manifest[group]
        }
    missing_required = [name for name, item in groups["required"].items() if not item["installed"]]
    result = {
        "profile": manifest["profile"],
        "ready": not missing_required,
        "missing_required": missing_required,
        "groups": groups,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if missing_required:
        raise SystemExit(1)


if __name__ == "__main__":
    main()


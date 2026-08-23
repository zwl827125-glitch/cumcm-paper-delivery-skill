from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import sys
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
MANIFEST = SKILL_DIR / "references" / "dependency-manifest.json"
BUNDLED_DIR = SKILL_DIR / "dependencies"


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
            if not match:
                continue
            name = match.group(1).strip()
            found.setdefault(name, str(path))
            parts = list(path.parts)
            if "cache" in parts:
                cache_index = parts.index("cache")
                if len(parts) > cache_index + 2:
                    plugin_name = parts[cache_index + 2]
                    found.setdefault(f"{plugin_name}:{name}", str(path))
    return found


def bundled_location(name: str, installed: dict[str, str]) -> str | None:
    if name in installed:
        return installed[name]
    candidate = BUNDLED_DIR / name
    if candidate.is_dir() and any(candidate.rglob("*")):
        return str(candidate)
    return None


def has_windows_progid(name: str) -> bool:
    if os.name != "nt":
        return False
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, rf"{name}\CLSID"):
            return True
    except OSError:
        return False


def has_module(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    installed = discover_skill_names()

    groups: dict[str, dict[str, dict[str, object]]] = {}
    for group in ("bundled_required", "bundled_optional", "codex_optional"):
        groups[group] = {}
        for name in manifest[group]:
            path = bundled_location(name, installed) if group.startswith("bundled") else installed.get(name)
            groups[group][name] = {"available": path is not None, "path": path}

    word_com = has_windows_progid("Word.Application")
    excel_com = has_windows_progid("Excel.Application")
    runtime = {
        "word": {
            "ready": word_com
            or groups["codex_optional"]["documents:documents"]["available"]
            or has_module("docx"),
            "word_com": word_com,
            "codex_documents": groups["codex_optional"]["documents:documents"]["available"],
            "python_docx": has_module("docx"),
            "pandoc": shutil.which("pandoc"),
            "libreoffice": shutil.which("libreoffice") or shutil.which("soffice"),
        },
        "pdf": {
            "ready": groups["codex_optional"]["pdf:pdf"]["available"]
            or has_module("pypdf")
            or has_module("pdfplumber"),
            "codex_pdf": groups["codex_optional"]["pdf:pdf"]["available"],
            "pypdf": has_module("pypdf"),
            "pdfplumber": has_module("pdfplumber"),
        },
        "spreadsheet": {
            "ready": excel_com
            or groups["codex_optional"]["spreadsheets:Spreadsheets"]["available"]
            or has_module("openpyxl"),
            "excel_com": excel_com,
            "codex_spreadsheets": groups["codex_optional"]["spreadsheets:Spreadsheets"]["available"],
            "openpyxl": has_module("openpyxl"),
        },
    }

    missing_bundled = [
        name for name, item in groups["bundled_required"].items() if not item["available"]
    ]
    missing_runtime = [name for name, item in runtime.items() if not item["ready"]]
    result = {
        "profile": manifest["profile"],
        "ready": not missing_bundled and not missing_runtime,
        "missing_bundled": missing_bundled,
        "missing_runtime": missing_runtime,
        "groups": groups,
        "runtime": runtime,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["ready"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

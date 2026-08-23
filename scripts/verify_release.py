from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "references" / "dependency-manifest.json"
CHECKSUMS = ROOT / "PAPER_CHECKSUMS.sha256"
PAPER_ROOT = ROOT / "dependencies" / "math-modeling" / "references" / "Outstanding Thesis" / "CUMCM"
MAX_GITHUB_FILE = 100 * 1024 * 1024


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_checksums() -> dict[str, str]:
    entries: dict[str, str] = {}
    for line in CHECKSUMS.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, relative = line.split("  ", 1)
        entries[relative] = digest
    return entries


def skill_name(path: Path) -> str | None:
    text = path.read_text(encoding="utf-8")
    match = re.search(r"(?m)^name:\s*([^\r\n]+)$", text[:4096])
    return match.group(1).strip().strip("\"'") if match else None


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    failures: list[str] = []
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    for name in manifest["bundled_required"] + manifest["bundled_optional"]:
        package = ROOT / "dependencies" / name
        if not package.is_dir():
            failures.append(f"缺少内置依赖目录：{name}")

    checksum_entries = parse_checksums()
    paper_files = sorted(PAPER_ROOT.rglob("*.pdf"))
    if len(paper_files) != 23:
        failures.append(f"CUMCM PDF 数量应为 23，实际为 {len(paper_files)}")
    if len(checksum_entries) != 23:
        failures.append(f"哈希清单数量应为 23，实际为 {len(checksum_entries)}")
    for relative, expected in checksum_entries.items():
        path = ROOT / Path(relative)
        if not path.is_file():
            failures.append(f"哈希清单文件不存在：{relative}")
            continue
        actual = sha256(path)
        if actual != expected:
            failures.append(f"哈希不一致：{relative}")

    forbidden = [
        ROOT / "dependencies" / "math-modeling" / "tools" / "docx",
        ROOT / "dependencies" / "math-modeling" / "tools" / "pdf",
        ROOT / "dependencies" / "math-modeling" / "tools" / "xlsx",
    ]
    for path in forbidden:
        if path.exists():
            failures.append(f"检测到未获准再分发目录：{path.relative_to(ROOT)}")

    figures4papers = ROOT / "dependencies" / "nature-figure" / "assets" / "figures4papers"
    third_party_files = [path for path in figures4papers.rglob("*") if path.is_file() and path.name != "README.md"]
    if third_party_files:
        failures.append("nature-figure/assets/figures4papers 中存在 README 之外的第三方文件")

    names: dict[str, str] = {}
    for path in sorted(ROOT.rglob("SKILL.md")):
        name = skill_name(path)
        relative = path.relative_to(ROOT).as_posix()
        if not name:
            failures.append(f"SKILL.md 缺少 name：{relative}")
            continue
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
            failures.append(f"Skill name 不符合 hyphen-case：{name} ({relative})")
        if name in names:
            failures.append(f"Skill name 重复：{name} ({names[name]} / {relative})")
        names[name] = relative
        head = path.read_text(encoding="utf-8")[:4096].lower()
        if "license: proprietary" in head:
            failures.append(f"检测到 Proprietary Skill：{relative}")

    unwanted = []
    oversized = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or ".git" in path.parts:
            continue
        if "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo", ".tmp", ".bak"} or path.name == ".env":
            unwanted.append(path.relative_to(ROOT).as_posix())
        if path.stat().st_size >= MAX_GITHUB_FILE:
            oversized.append(path.relative_to(ROOT).as_posix())
    if oversized:
        failures.append(f"存在不适合 GitHub 的超大文件：{oversized}")

    result = {
        "ok": not failures,
        "skill_count": len(names),
        "skills": names,
        "paper_count": len(paper_files),
        "checksum_count": len(checksum_entries),
        "repository_mib": round(
            sum(path.stat().st_size for path in ROOT.rglob("*") if path.is_file() and ".git" not in path.parts)
            / (1024 * 1024),
            2,
        ),
        "ignored_artifacts": unwanted,
        "failures": failures,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

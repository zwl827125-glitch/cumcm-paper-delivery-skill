from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent
MAIN_FILES = (
    "SKILL.md",
    "VERSION",
    "requirements.txt",
    "LICENSE",
    "NOTICE.md",
    "RIGHTS_AND_SOURCES.md",
    "PAPER_CHECKSUMS.sha256",
)
MAIN_DIRS = ("agents", "references", "scripts")


def default_target() -> Path:
    codex_home = os.environ.get("CODEX_HOME")
    base = Path(codex_home).expanduser() if codex_home else Path.home() / ".codex"
    return base / "skills"


def validate_target(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if resolved == Path(resolved.anchor):
        raise ValueError("拒绝把文件系统根目录作为 Skills 安装目标")
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def copy_tree(source: Path, destination: Path, force: bool) -> None:
    if destination.exists() and not force:
        raise FileExistsError(f"目标已存在：{destination}；更新时请加 --force")
    destination.mkdir(parents=True, exist_ok=True)
    for source_file in source.rglob("*"):
        if not source_file.is_file():
            continue
        relative = source_file.relative_to(source)
        if ".git" in relative.parts or "__pycache__" in relative.parts or source_file.suffix == ".pyc":
            continue
        target_file = destination / relative
        target_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_file, target_file)


def install(target_root: Path, force: bool) -> dict[str, object]:
    target = validate_target(target_root)
    main_destination = target / "cumcm-paper-delivery"
    if main_destination.exists() and not force:
        raise FileExistsError(f"目标已存在：{main_destination}；更新时请加 --force")
    main_destination.mkdir(parents=True, exist_ok=True)

    for name in MAIN_FILES:
        shutil.copy2(REPO_ROOT / name, main_destination / name)
    for name in MAIN_DIRS:
        copy_tree(REPO_ROOT / name, main_destination / name, force)

    installed = ["cumcm-paper-delivery"]
    for source in sorted((REPO_ROOT / "dependencies").iterdir(), key=lambda item: item.name):
        if not source.is_dir():
            continue
        copy_tree(source, target / source.name, force)
        installed.append(source.name)

    return {
        "target_root": str(target),
        "installed": installed,
        "count": len(installed),
        "updated_existing": force,
    }


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="安装 CUMCM 完整 Skill 包")
    parser.add_argument("--target", type=Path, default=default_target())
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    print(json.dumps(install(args.target, args.force), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

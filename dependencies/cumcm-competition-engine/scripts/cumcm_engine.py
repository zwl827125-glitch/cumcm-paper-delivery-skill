#!/usr/bin/env python3
"""Deterministic state, freeze, and audit helper for CUMCM projects.

The script intentionally uses only the Python standard library.  It does not
decide whether a mathematical model is good; it makes project evidence and
human approvals explicit, detects drift, and blocks an internally inconsistent
submission from being locked.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import unicodedata
import uuid
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = 1
STAGES = ("intake", "design", "solve", "verify", "write", "review", "delivery")
GATES = (
    "problem_selection",
    "model_contract",
    "result_freeze",
    "review_close",
    "submission_lock",
)
GATE_STAGE = {
    "problem_selection": "intake",
    "model_contract": "design",
    "result_freeze": "verify",
    "review_close": "review",
    "submission_lock": "delivery",
}
AFFECTS_GATE = {
    "intake": "problem_selection",
    "design": "model_contract",
    "solve": "result_freeze",
    "verify": "result_freeze",
    "write": "review_close",
    "review": "review_close",
    "delivery": "submission_lock",
    "none": None,
}
CODE_SUFFIXES = {
    ".py",
    ".m",
    ".r",
    ".jl",
    ".ipynb",
    ".cpp",
    ".c",
    ".java",
    ".js",
    ".ts",
    ".go",
    ".rs",
    ".scala",
    ".sh",
    ".bat",
    ".cmd",
    ".ps1",
    ".xlsx",
    ".xlsm",
    ".xls",
    ".xlsb",
    ".ods",
    ".sps",
    ".sav",
    ".spv",
    ".sas",
    ".do",
    ".mlx",
    ".nb",
    ".wl",
    ".gms",
    ".mod",
    ".lg4",
    ".slx",
    ".mw",
}
INTERACTIVE_SUFFIXES = {
    ".xlsx",
    ".xlsm",
    ".xls",
    ".xlsb",
    ".ods",
    ".sps",
    ".sav",
    ".spv",
    ".mlx",
    ".nb",
    ".wl",
    ".gms",
    ".mod",
    ".lg4",
    ".slx",
    ".mw",
}
PATH_LIKE_SUFFIXES = CODE_SUFFIXES | {
    ".csv",
    ".tsv",
    ".txt",
    ".json",
    ".jsonl",
    ".yaml",
    ".yml",
    ".xml",
    ".dat",
    ".parquet",
    ".feather",
    ".npy",
    ".npz",
    ".mat",
    ".pkl",
    ".pickle",
    ".sqlite",
    ".db",
    ".svg",
    ".png",
    ".jpg",
    ".jpeg",
    ".pdf",
}
PAPER_SUFFIXES = {".md", ".docx", ".doc", ".tex", ".pdf"}
TEXT_SUFFIXES = {
    ".txt",
    ".md",
    ".csv",
    ".tsv",
    ".json",
    ".jsonl",
    ".yaml",
    ".yml",
    ".py",
    ".m",
    ".r",
    ".jl",
    ".tex",
}
MAX_SUBMISSION_BYTES = 20_000_000
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 200_000_000
MAX_ARCHIVE_MEMBERS = 10_000
OFFICIAL_AI_DETAIL_NAME = "AI工具使用详情.pdf"
EPHEMERAL_SUFFIXES = {".pyc", ".pyo", ".tmp", ".swp"}
EPHEMERAL_NAMES = {".ds_store", "thumbs.db", "desktop.ini"}
RUNTIME_INPUT_BASES = ("work/intake", "work/modeling", "work/code")
RUNTIME_OUTPUT_BASES = ("work/results", "work/figures")
TRUSTED_LAUNCHER_NAMES = {
    "python",
    "python.exe",
    "python3",
    "python3.exe",
    "py",
    "py.exe",
    "powershell",
    "powershell.exe",
    "pwsh",
    "pwsh.exe",
    "r",
    "r.exe",
    "rscript",
    "rscript.exe",
    "julia",
    "julia.exe",
    "node",
    "node.exe",
    "matlab",
    "matlab.exe",
    "octave",
    "octave.exe",
    "octave-cli",
    "octave-cli.exe",
    "wolframscript",
    "wolframscript.exe",
    "gams",
    "gams.exe",
    "glpsol",
    "glpsol.exe",
    "cbc",
    "cbc.exe",
    "bash",
    "bash.exe",
    "sh",
    "sh.exe",
}

OFFICIAL_2026_SOURCES = [
    {
        "id": "cumcm-2026-rules",
        "title": "全国大学生数学建模竞赛参赛规则（2026年修订稿）",
        "url": "https://www.mcm.edu.cn/html_cn/node/9d8e511fe7a1447b35f53a82c908e2e0.html",
        "revision_date": "2026-03-03",
        "effective_date": "2026-03-01",
        "status": "unverified",
    },
    {
        "id": "cumcm-2026-format",
        "title": "全国大学生数学建模竞赛论文格式规范（2026年修订稿）",
        "url": "https://www.mcm.edu.cn/html_cn/node/4cd596519c9eb9fbd866398f6df0caa3.html",
        "revision_date": "2026-03-03",
        "effective_date": "2026-03-03",
        "status": "unverified",
    },
    {
        "id": "cumcm-2026-ai",
        "title": "全国大学生数学建模竞赛人工智能工具使用规定（2026年试行）",
        "url": "https://www.mcm.edu.cn/html_cn/node/fef94648f2836ab6cc81586f4c38512b.html",
        "revision_date": "2026-08-03",
        "effective_date": "2026-09-01",
        "status": "unverified",
    },
]


class EngineError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def current_schema(value: Any) -> bool:
    """JSON booleans compare equal to 1 in Python, so reject them explicitly."""
    return isinstance(value, int) and not isinstance(value, bool) and value == SCHEMA_VERSION


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise EngineError(f"缺少文件: {path}") from exc
    except json.JSONDecodeError as exc:
        raise EngineError(f"JSON 无法解析: {path}: {exc}") from exc


def read_json_or(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return read_json(path)


def project_root(raw: str | Path) -> Path:
    root = Path(raw).expanduser().resolve()
    if not (root / "cumcm-project.json").is_file():
        raise EngineError(f"不是已初始化的 CUMCM 项目: {root}")
    return root


def safe_project_path(root: Path, relative: str | Path) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute():
        raise EngineError(f"项目账本不得使用绝对路径: {candidate}")
    resolved = (root / candidate).resolve()
    try:
        common = Path(os.path.commonpath([str(root.resolve()), str(resolved)]))
    except ValueError as exc:
        raise EngineError(f"路径不在项目内: {candidate}") from exc
    if common != root.resolve():
        raise EngineError(f"路径越出项目目录: {candidate}")
    return resolved


def path_under_any(root: Path, path: Path, relative_bases: Iterable[str]) -> bool:
    resolved = path.resolve()
    for relative in relative_bases:
        base = (root / relative).resolve()
        try:
            resolved.relative_to(base)
            return True
        except ValueError:
            continue
    return False


def relative_posix(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def iter_regular_files(base: Path) -> Iterable[Path]:
    if not base.exists():
        return []
    files: list[Path] = []
    for path in base.rglob("*"):
        if path.is_symlink():
            raise EngineError(f"冻结/提交范围内不允许符号链接: {path}")
        if path.is_file():
            files.append(path)
    return sorted(files, key=lambda item: item.as_posix().casefold())


def is_ephemeral_file(path: Path) -> bool:
    return (
        any(part.casefold() == "__pycache__" for part in path.parts)
        or path.name.casefold() in EPHEMERAL_NAMES
        or path.suffix.casefold() in EPHEMERAL_SUFFIXES
        or path.name.startswith("~$")
    )


def iter_evidence_files(base: Path) -> list[Path]:
    return [path for path in iter_regular_files(base) if not is_ephemeral_file(path)]


def read_jsonl(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    records: list[dict[str, Any]] = []
    errors: list[str] = []
    if not path.exists():
        return records, errors
    for number, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            errors.append(f"第 {number} 行: {exc}")
            continue
        if not isinstance(value, dict):
            errors.append(f"第 {number} 行不是 JSON object")
            continue
        records.append(value)
    return records, errors


def append_chained_event(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    records, errors = read_jsonl(path)
    if errors:
        raise EngineError(f"事件账本已有损坏，拒绝追加: {'; '.join(errors)}")
    chain_ok, chain_errors, _ = verify_event_chain(path)
    if not chain_ok:
        raise EngineError(f"事件账本哈希链已有损坏，拒绝追加: {'; '.join(chain_errors)}")
    previous_hash = records[-1].get("event_hash", "GENESIS") if records else "GENESIS"
    event = {
        "schema_version": SCHEMA_VERSION,
        "event_id": str(uuid.uuid4()),
        "timestamp": utc_now(),
        **payload,
        "previous_hash": previous_hash,
    }
    event["event_hash"] = hashlib.sha256(canonical_json(event)).hexdigest()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
    return event


def verify_event_chain(path: Path) -> tuple[bool, list[str], list[dict[str, Any]]]:
    records, errors = read_jsonl(path)
    previous = "GENESIS"
    seen_event_ids: set[str] = set()
    for index, record in enumerate(records, 1):
        if not current_schema(record.get("schema_version")):
            errors.append(f"第 {index} 条 schema_version 不受支持")
        event_id = record.get("event_id")
        if not valid_uuid_text(event_id):
            errors.append(f"第 {index} 条 event_id 不是规范 UUID")
        elif event_id in seen_event_ids:
            errors.append(f"第 {index} 条 event_id 重复")
        else:
            seen_event_ids.add(event_id)
        timestamp = record.get("timestamp")
        if not nonempty_text(timestamp):
            errors.append(f"第 {index} 条 timestamp 为空")
        else:
            try:
                datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            except ValueError:
                errors.append(f"第 {index} 条 timestamp 不是 ISO-8601")
        if record.get("previous_hash") != previous:
            errors.append(f"第 {index} 条 previous_hash 不连续")
        stored_hash = record.get("event_hash")
        if not isinstance(stored_hash, str) or not re.fullmatch(
            r"[0-9a-f]{64}", stored_hash
        ):
            errors.append(f"第 {index} 条 event_hash 格式不合法")
        body = dict(record)
        body.pop("event_hash", None)
        expected_hash = hashlib.sha256(canonical_json(body)).hexdigest()
        if stored_hash != expected_hash:
            errors.append(f"第 {index} 条 event_hash 不匹配")
        previous = stored_hash or "BROKEN"
    return not errors, errors, records


def gate_data(root: Path) -> dict[str, Any]:
    value = read_json_or(root / "state" / "human_gates.json", {"gates": {}})
    if not isinstance(value, dict):
        return {"gates": {}}
    if not isinstance(value.get("gates"), dict):
        value = dict(value)
        value["gates"] = {}
    return value


def gate_evidence_scope(root: Path, gate: str) -> list[Path]:
    """Select evidence whose drift invalidates a recorded human approval."""
    files: list[Path] = []

    def add_file(relative: str) -> None:
        path = root / relative
        if path.is_file():
            files.append(path)

    def add_tree(relative: str) -> None:
        files.extend(iter_evidence_files(root / relative))

    for relative in (
        "cumcm-project.json",
        "state/rules_manifest.json",
        "state/problem_contract.json",
    ):
        add_file(relative)
    add_tree("work/intake")
    if GATES.index(gate) >= GATES.index("model_contract"):
        add_file("state/model_contract.json")
        add_file("state/decision_ledger.jsonl")
        add_tree("work/modeling")
    if GATES.index(gate) >= GATES.index("result_freeze"):
        for relative in (
            "state/decision_ledger.jsonl",
            "state/run_manifest.json",
            "state/result_ledger.json",
            "state/verification_report.json",
        ):
            add_file(relative)
        for relative in ("work/code", "work/results", "work/figures"):
            add_tree(relative)
    if GATES.index(gate) >= GATES.index("review_close"):
        add_file("state/claim_evidence.json")
        add_tree("state/reviews")
        add_tree("paper")
    if gate == "submission_lock":
        files = [
            path
            for path in final_lock_scope(root)
            if relative_posix(root, path) != "state/human_gates.json"
            and not relative_posix(root, path).startswith("reports/audit_")
        ]
    unique = {relative_posix(root, path): path for path in files}
    return [unique[key] for key in sorted(unique, key=str.casefold)]


def gate_evidence_digest(root: Path, gate: str) -> tuple[str, list[str]]:
    manifest = build_hash_manifest(root, gate_evidence_scope(root, gate))
    paths = [item["path"] for item in manifest]
    return hashlib.sha256(canonical_json(manifest)).hexdigest(), paths


def gate_is_approved(root: Path, gate: str) -> bool:
    data = gate_data(root)
    if not current_schema(data.get("schema_version")):
        return False
    item = data.get("gates", {}).get(gate, {})
    if not isinstance(item, dict) or item.get("approved") is not True:
        return False
    if (
        not nonempty_text(item.get("approved_by"))
        or not valid_iso_timestamp(item.get("approved_at"))
        or not nonempty_text(item.get("note"))
    ):
        return False
    config = read_json_or(root / "cumcm-project.json", {})
    mode = config.get("mode") if isinstance(config, dict) else None
    approval_kind_ok = False
    if mode == "training":
        approval_kind_ok = item.get("approval_kind") == "simulation"
    elif mode == "competition":
        approval_kind_ok = (
            item.get("approval_kind") == "team_attested"
            and nonempty_text(item.get("approved_by"))
            and not reserved_approver(item.get("approved_by"))
        )
    if not approval_kind_ok or not nonempty_text(item.get("evidence_sha256")):
        return False
    try:
        digest, paths = gate_evidence_digest(root, gate)
    except Exception:
        return False
    return digest == item.get("evidence_sha256") and paths == item.get("evidence_files")


def ensure_unlocked(root: Path) -> None:
    if (root / "reports" / "final_lock.json").exists():
        raise EngineError("项目已最终锁定；先使用 reopen 并记录理由")


def initial_rules(year: int) -> dict[str, Any]:
    sources = [dict(item) for item in OFFICIAL_2026_SOURCES] if year == 2026 else []
    return {
        "schema_version": SCHEMA_VERSION,
        "competition": "CUMCM",
        "year": year,
        "verified_at": None,
        "verified_by": None,
        "confirmed_for_year": None,
        "sources": sources,
        "region_rules": [],
        "classification": {
            "official_hard": "当届官方明确要求",
            "project_required": "本项目可复现与一致性门禁",
            "quality_advisory": "可说明理由后偏离的质量建议",
        },
        "notes": "正式项目须打开当届官网逐项核验后再把 source.status 改为 verified。",
    }


def initialize(raw_root: str, year: int, mode: str) -> Path:
    if (
        not isinstance(year, int)
        or isinstance(year, bool)
        or year < 2000
        or year > 2100
    ):
        raise EngineError("year 必须是 2000–2100 之间的四位年份")
    if mode not in {"competition", "training"}:
        raise EngineError("mode 必须是 competition 或 training")
    root = Path(raw_root).expanduser().resolve()
    if root.exists() and not root.is_dir():
        raise EngineError(f"初始化目标不是目录: {root}")
    config_path = root / "cumcm-project.json"
    if config_path.exists() or config_path.is_symlink():
        raise EngineError(f"项目已初始化，拒绝覆盖: {config_path}")
    managed_roots = tuple(
        root / name
        for name in ("state", "work", "paper", "supporting", "delivery", "reports")
    )
    conflicts = [
        str(path)
        for path in managed_roots
        if path.exists() or path.is_symlink()
    ]
    if conflicts:
        raise EngineError(
            "检测到已有托管路径，拒绝初始化覆盖；请迁移后再初始化或选择新目录: "
            + ", ".join(conflicts)
        )
    root.mkdir(parents=True, exist_ok=True)
    for relative in (
        "state/reviews",
        "work/intake",
        "work/modeling",
        "work/code",
        "work/results",
        "work/figures",
        "paper",
        "supporting",
        "delivery",
        "reports/history",
    ):
        (root / relative).mkdir(parents=True, exist_ok=True)

    config = {
        "schema_version": SCHEMA_VERSION,
        "competition": "CUMCM",
        "year": year,
        "mode": mode,
        "created_at": utc_now(),
        "paths": {
            "state": "state",
            "code": "work/code",
            "results": "work/results",
            "figures": "work/figures",
            "paper": "paper",
            "supporting": "supporting",
            "delivery": "delivery",
            "reports": "reports",
        },
    }
    write_json(config_path, config)
    write_json(root / "state" / "rules_manifest.json", initial_rules(year))
    write_json(
        root / "state" / "problem_contract.json",
        {
            "schema_version": SCHEMA_VERSION,
            "problem_code": "",
            "problem_title": "",
            "problem_group": "",
            "questions": [],
            "data_inventory": [],
            "unknowns": [],
            "assumptions_to_test": [],
            "risk_register": [],
        },
    )
    write_json(
        root / "state" / "model_contract.json",
        {"schema_version": SCHEMA_VERSION, "questions": {}, "global_dependencies": []},
    )
    write_json(
        root / "state" / "run_manifest.json",
        {
            "schema_version": SCHEMA_VERSION,
            "program_usage": "undetermined",
            "entrypoint": "",
            "command": "",
            "environment": {},
            "randomness": {"mode": "undetermined", "seeds": []},
            "declared_inputs": [],
            "official_attachment_inputs": [],
            "expected_outputs": [],
            "manual_replay_procedure": "",
            "no_program_reason": "",
        },
    )
    write_json(
        root / "state" / "result_ledger.json",
        {"schema_version": SCHEMA_VERSION, "results": []},
    )
    write_json(
        root / "state" / "verification_report.json",
        {"schema_version": SCHEMA_VERSION, "questions": {}},
    )
    write_json(
        root / "state" / "claim_evidence.json",
        {"schema_version": SCHEMA_VERSION, "claims": []},
    )
    write_json(
        root / "state" / "compliance_attestation.json",
        {
            "schema_version": SCHEMA_VERSION,
            "final_paper": "",
            "support_required": None,
            "no_support_reason": "",
            "support_archive": "",
            "support_manifest": "",
            "ai_declaration_mode": "undetermined",
            "ai_detail_pdf": f"supporting/{OFFICIAL_AI_DETAIL_NAME}",
            "forbidden_identity_terms": [],
            "checks": {
                "official_rules_rechecked_on_submission_day": False,
                "paper_and_print_match": False,
                "abstract_page_checked": False,
                "body_page_limit_checked": False,
                "anonymous_checked": False,
                "citations_checked": False,
                "appendix_checked": False,
                "support_replayed": False,
                "archive_contents_checked": False,
                "ai_declaration_checked": False,
                "ai_usage_truth_confirmed": False,
                "final_render_checked": False,
            },
        },
    )
    write_json(
        root / "state" / "human_gates.json",
        {
            "schema_version": SCHEMA_VERSION,
            "gates": {
                gate: {
                    "approved": False,
                    "approved_by": None,
                    "approved_at": None,
                    "approval_kind": None,
                    "note": None,
                    "evidence_sha256": None,
                    "evidence_files": [],
                }
                for gate in GATES
            },
        },
    )
    (root / "state" / "decision_ledger.jsonl").touch(exist_ok=False)
    (root / "state" / "ai_usage_log.jsonl").touch(exist_ok=False)
    (root / "state" / "change_log.jsonl").touch(exist_ok=False)
    return root


def add_finding(
    findings: list[dict[str, Any]],
    finding_id: str,
    rule_class: str,
    passed: bool,
    message: str,
    evidence: Any = None,
    remediation: str = "",
    severity: str = "blocker",
    status: str | None = None,
) -> None:
    resolved_status = status or ("pass" if passed else "fail")
    resolved = resolved_status in {"pass", "not_applicable"}
    findings.append(
        {
            "id": finding_id,
            "class": rule_class,
            "status": resolved_status,
            "severity": "note" if resolved else severity,
            "message": message,
            "evidence": evidence,
            "remediation": "" if resolved else remediation,
        }
    )


def nonempty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def valid_iso_timestamp(value: Any) -> bool:
    if not nonempty_text(value):
        return False
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is not None
    except (TypeError, ValueError):
        return False


def valid_uuid_text(value: Any) -> bool:
    if not nonempty_text(value):
        return False
    try:
        return str(uuid.UUID(value)) == value.casefold()
    except (AttributeError, ValueError):
        return False


def contains_nonfinite_number(value: Any) -> bool:
    if isinstance(value, float):
        return not math.isfinite(value)
    if isinstance(value, list):
        return any(contains_nonfinite_number(item) for item in value)
    if isinstance(value, dict):
        return any(contains_nonfinite_number(item) for item in value.values())
    return False


def positive_finite_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return value > 0
    if isinstance(value, float):
        return math.isfinite(value) and value > 0
    return False


def meaningful_json_value(value: Any) -> bool:
    """Reject null, blank text, empty containers, and non-finite results."""
    if value is None or contains_nonfinite_number(value):
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return bool(value)
    return True


def question_ids(root: Path) -> list[str]:
    raw_problem = read_json_or(root / "state" / "problem_contract.json", {})
    problem = raw_problem if isinstance(raw_problem, dict) else {}
    values: list[str] = []
    for question in problem.get("questions", []):
        if isinstance(question, dict) and nonempty_text(question.get("id")):
            values.append(question["id"].strip())
    return values


def validate_declared_paths(
    root: Path,
    raw_values: Any,
    label: str,
    allowed_bases: tuple[str, ...],
    *,
    require_files: bool,
) -> tuple[list[str], list[str]]:
    """Validate a manifest path array and return canonical project-relative paths."""
    errors: list[str] = []
    normalized: list[str] = []
    if not isinstance(raw_values, list):
        return [], [f"{label} 必须是列表"]
    for value in raw_values:
        if not nonempty_text(value):
            errors.append(f"{label} 含空路径")
            continue
        try:
            path = safe_project_path(root, value)
            relative = relative_posix(root, path)
            normalized.append(relative)
            if not path_under_any(root, path, allowed_bases):
                errors.append(f"{label} 路径不在允许目录: {value}")
            elif is_ephemeral_file(path):
                errors.append(f"{label} 不得包含临时/系统文件: {value}")
            elif require_files and (not path.is_file() or path.is_symlink()):
                errors.append(f"{label} 文件不存在或不是普通文件: {value}")
        except EngineError as exc:
            errors.append(str(exc))
    if len(normalized) != len(set(normalized)):
        errors.append(f"{label} 含重复路径")
    return normalized, errors


def validate_official_attachment_inputs(
    root: Path, raw_values: Any, declared_inputs: list[str]
) -> tuple[list[dict[str, str]], list[str]]:
    """Validate official problem attachments that need replay but not resubmission."""
    errors: list[str] = []
    normalized: list[dict[str, str]] = []
    if not isinstance(raw_values, list):
        return [], ["official_attachment_inputs 必须是列表"]
    declared_set = set(declared_inputs)
    seen: set[str] = set()
    for index, item in enumerate(raw_values):
        if not isinstance(item, dict) or set(item) != {"path", "source_ref"}:
            errors.append(
                f"official_attachment_inputs[{index}] 必须且只能包含 path/source_ref"
            )
            continue
        if not nonempty_text(item.get("path")) or not nonempty_text(
            item.get("source_ref")
        ):
            errors.append(
                f"official_attachment_inputs[{index}] 的 path/source_ref 必须是非空文本"
            )
            continue
        try:
            path = safe_project_path(root, item["path"])
            relative = relative_posix(root, path)
        except EngineError as exc:
            errors.append(str(exc))
            continue
        if not path_under_any(root, path, ("work/intake",)):
            errors.append(f"官方赛题附件必须位于 work/intake: {relative}")
        if relative not in declared_set:
            errors.append(f"官方赛题附件未同时列入 declared_inputs: {relative}")
        if relative in seen:
            errors.append(f"official_attachment_inputs 含重复路径: {relative}")
        seen.add(relative)
        normalized.append(
            {"path": relative, "source_ref": item["source_ref"].strip()}
        )
    return normalized, errors


def validate_data_inventory(
    root: Path, raw_values: Any
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    """Validate data provenance and return used self-sourced project files.

    Official problem attachments are exempt from resubmission. Data independently
    collected by the team and actually used are not, even when no program ran.
    """
    errors: list[str] = []
    normalized: list[dict[str, Any]] = []
    self_sourced_paths: list[str] = []
    if not isinstance(raw_values, list):
        return [], ["data_inventory 必须是列表"], []
    seen_ids: set[str] = set()
    required = {"id", "description", "origin", "used", "path", "source_ref"}
    origins = {"official_problem", "self_sourced", "generated", "none"}
    for index, item in enumerate(raw_values):
        if not isinstance(item, dict) or not required.issubset(item):
            errors.append(
                f"data_inventory[{index}] 必须含 id/description/origin/used/path/source_ref"
            )
            continue
        item_id = item.get("id")
        description = item.get("description")
        origin = item.get("origin")
        used = item.get("used")
        raw_path = item.get("path")
        source_ref = item.get("source_ref")
        row_errors: list[str] = []
        if not nonempty_text(item_id) or item_id in seen_ids:
            row_errors.append("id 为空或重复")
        else:
            seen_ids.add(item_id)
        if not nonempty_text(description):
            row_errors.append("description 为空")
        if origin not in origins:
            row_errors.append("origin 不受支持")
        if not isinstance(used, bool):
            row_errors.append("used 必须是 boolean")
        if not isinstance(raw_path, str) or not isinstance(source_ref, str):
            row_errors.append("path/source_ref 必须是字符串")
        normalized_path = raw_path if isinstance(raw_path, str) else ""
        if origin in {"official_problem", "self_sourced"} and used is True:
            if not nonempty_text(raw_path) or not nonempty_text(source_ref):
                row_errors.append("实际使用的外部数据必须登记 path/source_ref")
            else:
                try:
                    path = safe_project_path(root, raw_path)
                    normalized_path = relative_posix(root, path)
                    if not path_under_any(root, path, ("work/intake",)):
                        row_errors.append("外部数据必须位于 work/intake")
                    elif not path.is_file() or path.is_symlink() or is_ephemeral_file(path):
                        row_errors.append("外部数据 path 必须是现存普通文件")
                except EngineError as exc:
                    row_errors.append(str(exc))
        if origin == "self_sourced" and used is True and not row_errors:
            self_sourced_paths.append(normalized_path)
        if origin == "none" and (
            used is not False or raw_path != "" or source_ref != ""
        ):
            row_errors.append("origin=none 时 used=false 且 path/source_ref 必须为空")
        if row_errors:
            errors.append(f"data_inventory[{index}]: " + "; ".join(row_errors))
        normalized.append(
            {
                "id": item_id,
                "description": description,
                "origin": origin,
                "used": used,
                "path": normalized_path,
                "source_ref": source_ref,
            }
        )
    if len(self_sourced_paths) != len(set(self_sourced_paths)):
        errors.append("data_inventory 含重复的自主数据 path")
    return normalized, errors, sorted(set(self_sourced_paths))


def valid_environment(value: Any, program_usage: Any) -> bool:
    if program_usage == "none":
        return value == {}
    if not isinstance(value, dict) or not value:
        return False
    if any(not nonempty_text(key) for key in value):
        return False
    for item in value.values():
        if nonempty_text(item):
            continue
        if (
            isinstance(item, list)
            and bool(item)
            and all(nonempty_text(entry) for entry in item)
        ):
            continue
        return False
    keys = {str(key).casefold() for key in value}
    if program_usage == "interactive":
        return {"software", "version"}.issubset(keys)
    runtime_keys = {
        "python",
        "r",
        "julia",
        "matlab",
        "runtime",
        "interpreter",
        "compiler",
        "software",
    }
    return program_usage == "code" and bool(keys & runtime_keys)


def substantive_manual_procedure(value: Any) -> bool:
    if not nonempty_text(value) or len(value.strip()) < 40:
        return False
    steps = [
        item.strip()
        for item in re.split(r"(?:\r?\n|[;；])", value.strip())
        if item.strip()
    ]
    return len(steps) >= 2


def interactive_artifact_ok(path: Path) -> tuple[bool, str]:
    if not path.is_file() or path.is_symlink() or path.stat().st_size <= 0:
        return False, "交互入口不存在、为空或不是普通文件"
    suffix = path.suffix.casefold()
    if suffix not in INTERACTIVE_SUFFIXES:
        return False, f"交互入口类型不受支持: {suffix or '(none)'}"
    header = path.read_bytes()[:8]
    if suffix in {".xlsx", ".xlsm", ".ods", ".slx", ".mlx"} and not header.startswith(
        (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")
    ):
        return False, "交互入口的 ZIP/Office 文件签名不匹配"
    if suffix in {".xls", ".xlsb"} and not header.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        return False, "交互入口的 OLE 文件签名不匹配"
    return True, ""


def parse_command(command: Any) -> tuple[list[str], list[str]]:
    if not nonempty_text(command):
        return [], ["command 为空"]
    try:
        if os.name == "nt":
            import ctypes

            argument_count = ctypes.c_int()
            command_line_to_argv = ctypes.windll.shell32.CommandLineToArgvW
            command_line_to_argv.argtypes = [
                ctypes.c_wchar_p,
                ctypes.POINTER(ctypes.c_int),
            ]
            command_line_to_argv.restype = ctypes.POINTER(ctypes.c_wchar_p)
            pointer = command_line_to_argv(command, ctypes.byref(argument_count))
            if not pointer:
                raise ValueError("CommandLineToArgvW failed")
            try:
                argv = [pointer[index] for index in range(argument_count.value)]
            finally:
                ctypes.windll.kernel32.LocalFree(pointer)
        else:
            argv = shlex.split(command, posix=True)
    except (ValueError, OSError) as exc:
        return [], [f"command 无法解析: {exc}"]
    argv = [
        token[1:-1]
        if len(token) >= 2 and token[0] == token[-1] and token[0] in {'"', "'"}
        else token
        for token in argv
    ]
    return argv, ([] if argv else ["command 解析为空"])


def command_contract_errors(
    root: Path,
    run: dict[str, Any],
    declared_inputs: list[str],
    expected_outputs: list[str],
) -> tuple[list[str], list[str]]:
    """Require the command to invoke the declared project entrypoint only.

    This validates the command line and clean-workspace contract; it is not an
    operating-system process sandbox and therefore only trusted team code may run.
    """
    argv, errors = parse_command(run.get("command"))
    if not argv:
        return argv, errors
    entrypoint = run.get("entrypoint")
    if not nonempty_text(entrypoint):
        return argv, errors + ["entrypoint 为空"]
    try:
        entry_path = safe_project_path(root, entrypoint)
        entry_relative = relative_posix(root, entry_path)
    except EngineError as exc:
        return argv, errors + [str(exc)]

    executable_name = Path(argv[0]).name.casefold()
    eval_flags: dict[str, set[str]] = {
        "python": {"-c", "-m"},
        "python.exe": {"-c", "-m"},
        "python3": {"-c", "-m"},
        "python3.exe": {"-c", "-m"},
        "py": {"-c", "-m"},
        "py.exe": {"-c", "-m"},
        "powershell": {"-command", "-encodedcommand", "-c"},
        "powershell.exe": {"-command", "-encodedcommand", "-c"},
        "pwsh": {"-command", "-encodedcommand", "-c"},
        "pwsh.exe": {"-command", "-encodedcommand", "-c"},
        "node": {"-e", "--eval"},
        "node.exe": {"-e", "--eval"},
        "rscript": {"-e"},
        "rscript.exe": {"-e"},
        "bash": {"-c"},
        "bash.exe": {"-c"},
        "sh": {"-c"},
        "sh.exe": {"-c"},
        "matlab": {"-batch", "-r"},
        "matlab.exe": {"-batch", "-r"},
    }
    forbidden_flags = eval_flags.get(executable_name, set())
    if any(token.casefold() in forbidden_flags for token in argv[1:]):
        errors.append("command 使用内联求值/模块执行参数；请改用 work/code 下的包装入口")

    launcher_value = argv[0]
    launcher_candidate = Path(launcher_value)
    launcher_is_project_path = (
        "/" in launcher_value
        or "\\" in launcher_value
        or (not launcher_candidate.is_absolute() and (root / launcher_candidate).exists())
    )
    launcher_is_entrypoint = False
    if launcher_is_project_path and not launcher_candidate.is_absolute():
        try:
            launcher_project_path = safe_project_path(root, launcher_value)
            launcher_is_entrypoint = (
                relative_posix(root, launcher_project_path) == entry_relative
                and launcher_project_path.is_file()
                and path_under_any(root, launcher_project_path, ("work/code",))
            )
        except EngineError as exc:
            errors.append(str(exc))
    if not launcher_is_entrypoint and executable_name not in TRUSTED_LAUNCHER_NAMES:
        errors.append(
            "command 的 argv[0] 必须是受信解释器/建模运行器，或项目内已声明 entrypoint"
        )

    candidate_values: list[tuple[int, str]] = []
    for index, token in enumerate(argv):
        value = token.split("=", 1)[1] if token.startswith("-") and "=" in token else token
        candidate_values.append((index, value))
    normalized_candidates: list[str] = []
    declared_input_set = set(declared_inputs)
    expected_output_set = set(expected_outputs)
    for index, value in candidate_values:
        if not value or (index > 0 and value.startswith("-")):
            continue
        if index == 0 and not launcher_is_entrypoint:
            continue
        candidate = Path(value)
        if index > 0 and candidate.is_absolute():
            errors.append(f"command 参数不得使用绝对路径: {value}")
            continue
        if index > 0 and ".." in candidate.parts:
            errors.append(f"command 参数不得使用 .. 越界: {value}")
            continue
        path_like = (
            index == 0
            or "/" in value
            or "\\" in value
            or candidate.suffix.casefold() in PATH_LIKE_SUFFIXES
            or (root / candidate).exists()
        )
        if not path_like or (index == 0 and candidate.is_absolute()):
            continue
        try:
            project_path = safe_project_path(root, value)
            relative = relative_posix(root, project_path)
            normalized_candidates.append(relative)
        except EngineError as exc:
            errors.append(str(exc))
            continue
        if relative == entry_relative:
            continue
        if path_under_any(root, project_path, ("work/code",)):
            continue
        if path_under_any(root, project_path, ("work/intake", "work/modeling")):
            if relative not in declared_input_set:
                errors.append(f"command 引用未声明输入: {relative}")
            continue
        if path_under_any(root, project_path, RUNTIME_OUTPUT_BASES):
            if project_path.suffix and relative not in expected_output_set:
                errors.append(f"command 引用未声明输出: {relative}")
            continue
        if index > 0 or project_path.exists():
            errors.append(f"command 引用非运行清单托管路径: {relative}")
    if entry_relative not in normalized_candidates:
        errors.append("command 未绑定并执行已声明的 entrypoint")
    return argv, errors


def resolved_replay_argv(argv: list[str]) -> list[str]:
    """Resolve only the portable Python launcher aliases used by replay."""
    resolved = list(argv)
    if not resolved:
        return resolved
    launcher = Path(resolved[0]).name.casefold()
    python_launchers = {
        "python",
        "python.exe",
        "python3",
        "python3.exe",
        "py",
        "py.exe",
    }
    if launcher in python_launchers and not Path(resolved[0]).is_absolute():
        if launcher in {"py", "py.exe"} and len(resolved) > 1 and re.fullmatch(
            r"-\d+(?:\.\d+)?(?:-\d+)?", resolved[1]
        ):
            resolved.pop(1)
        resolved[0] = sys.executable
    return resolved


def replay_report_evidence(
    root: Path, *, require_current_freeze: bool
) -> tuple[list[str], dict[str, list[str]]]:
    def valid_hash_rows(raw: Any, *, require_fresh: bool) -> bool:
        return isinstance(raw, list) and all(
            isinstance(item, dict)
            and set(item)
            == ({"path", "size", "sha256", "freshly_created"} if require_fresh else {"path", "size", "sha256"})
            and nonempty_text(item.get("path"))
            and isinstance(item.get("size"), int)
            and not isinstance(item.get("size"), bool)
            and item.get("size", -1) >= 0
            and bool(re.fullmatch(r"[0-9a-f]{64}", str(item.get("sha256", ""))))
            and (not require_fresh or item.get("freshly_created") is True)
            for item in raw
        )

    run_path = root / "state" / "run_manifest.json"
    freeze_path = root / "state" / "frozen_manifest.json"
    raw_run = read_json_or(run_path, {})
    run = raw_run if isinstance(raw_run, dict) else {}
    current_run_sha256 = sha256_file(run_path) if run_path.is_file() else None
    current_freeze_sha256 = sha256_file(freeze_path) if freeze_path.is_file() else None
    current_engine_sha256 = sha256_file(Path(__file__).resolve())

    declared_inputs, input_errors = validate_declared_paths(
        root,
        run.get("declared_inputs"),
        "declared_inputs",
        RUNTIME_INPUT_BASES,
        require_files=True,
    )
    official_inputs, official_input_errors = validate_official_attachment_inputs(
        root, run.get("official_attachment_inputs"), declared_inputs
    )
    declared_outputs, output_errors = validate_declared_paths(
        root,
        run.get("expected_outputs"),
        "expected_outputs",
        RUNTIME_OUTPUT_BASES,
        require_files=True,
    )
    parsed_argv, command_errors = command_contract_errors(
        root, run, declared_inputs, declared_outputs
    )
    expected_resolved_argv = resolved_replay_argv(parsed_argv)
    current_contract_errors = (
        input_errors + official_input_errors + output_errors + command_errors
    )
    if not current_schema(run.get("schema_version")):
        current_contract_errors.append("run schema version")
    if run.get("program_usage") != "code":
        current_contract_errors.append("run program_usage")
    if not declared_outputs:
        current_contract_errors.append("expected_outputs empty")

    runtime_paths = list(iter_evidence_files(root / "work" / "code"))
    runtime_paths.extend(
        path
        for value in declared_inputs
        if (path := safe_project_path(root, value)).is_file()
    )
    runtime_map = {relative_posix(root, path): path for path in runtime_paths}
    expected_runtime_files = sorted(runtime_map)
    expected_runtime_evidence = build_hash_manifest(root, runtime_map.values())
    expected_output_evidence = [
        {
            "path": relative,
            "freshly_created": True,
            "size": safe_project_path(root, relative).stat().st_size,
            "sha256": sha256_file(safe_project_path(root, relative)),
        }
        for relative in declared_outputs
    ] if not output_errors else []

    frozen_output_map: dict[str, dict[str, Any]] = {}
    if freeze_path.is_file():
        raw_freeze = read_json_or(freeze_path, {})
        if isinstance(raw_freeze, dict):
            frozen_output_map = {
                item["path"]: item
                for item in raw_freeze.get("files", [])
                if isinstance(item, dict) and nonempty_text(item.get("path"))
            }

    required_fields = {
        "schema_version",
        "started_at",
        "finished_at",
        "declared_entrypoint",
        "declared_command",
        "declared_executable",
        "resolved_command",
        "isolated_workspace",
        "clean_workspace",
        "runtime_files",
        "runtime_evidence",
        "declared_inputs",
        "official_attachment_inputs",
        "timeout_seconds",
        "timed_out",
        "execution_error",
        "returncode",
        "stdout_tail",
        "stderr_tail",
        "expected_outputs",
        "project_output_mismatches",
        "unexpected_outputs",
        "unexpected_workspace_files",
        "runtime_input_drift",
        "solve_blockers",
        "run_manifest_sha256",
        "frozen_manifest_sha256",
        "freeze_checked",
        "freeze_valid",
        "freeze_details",
        "engine_sha256",
        "outcome",
        "report_path",
        "report_sha256",
    }
    passing: list[str] = []
    rejected: dict[str, list[str]] = {}
    for replay_path in sorted((root / "reports").glob("replay_*.json")):
        value = read_json_or(replay_path, {})
        reasons: list[str] = []
        relative_report = relative_posix(root, replay_path)
        if not isinstance(value, dict):
            reasons.append("report is not an object")
            value = {}
        missing_fields = sorted(required_fields - set(value))
        unexpected_fields = sorted(set(value) - required_fields)
        if missing_fields:
            reasons.append("missing fields: " + ", ".join(missing_fields))
        if unexpected_fields:
            reasons.append("unexpected fields: " + ", ".join(unexpected_fields))
        if current_contract_errors:
            reasons.append("current run contract invalid")
        if not current_schema(value.get("schema_version")):
            reasons.append("schema version")
        if value.get("outcome") != "PASS":
            reasons.append("outcome")
        if not nonempty_text(value.get("started_at")) or not nonempty_text(value.get("finished_at")):
            reasons.append("timestamps")
        else:
            try:
                started = datetime.fromisoformat(value["started_at"].replace("Z", "+00:00"))
                finished = datetime.fromisoformat(value["finished_at"].replace("Z", "+00:00"))
                if started.tzinfo is None or finished.tzinfo is None or finished < started:
                    reasons.append("timestamps")
            except (TypeError, ValueError):
                reasons.append("timestamps")
        if value.get("declared_entrypoint") != run.get("entrypoint"):
            reasons.append("entrypoint drift")
        if value.get("declared_command") != run.get("command"):
            reasons.append("command drift")
        if value.get("declared_executable") != (
            parsed_argv[0] if parsed_argv else None
        ):
            reasons.append("declared executable")
        if (
            value.get("resolved_command") != expected_resolved_argv
            or not isinstance(value.get("resolved_command"), list)
            or not all(nonempty_text(item) for item in value.get("resolved_command", []))
        ):
            reasons.append("resolved command")
        if value.get("isolated_workspace") is not True or value.get(
            "clean_workspace"
        ) is not True:
            reasons.append("not clean isolated workspace")
        if value.get("runtime_files") != expected_runtime_files:
            reasons.append("runtime files")
        if (
            not valid_hash_rows(value.get("runtime_evidence"), require_fresh=False)
            or value.get("runtime_evidence") != expected_runtime_evidence
        ):
            reasons.append("runtime evidence")
        if value.get("declared_inputs") != declared_inputs:
            reasons.append("declared inputs")
        if value.get("official_attachment_inputs") != official_inputs:
            reasons.append("official attachment inputs")
        if (
            not isinstance(value.get("timeout_seconds"), int)
            or isinstance(value.get("timeout_seconds"), bool)
            or value.get("timeout_seconds", 0) < 1
        ):
            reasons.append("timeout")
        if (
            value.get("returncode") != 0
            or not isinstance(value.get("returncode"), int)
            or isinstance(value.get("returncode"), bool)
            or value.get("timed_out") is not False
        ):
            reasons.append("execution")
        if value.get("execution_error") != "":
            reasons.append("execution error")
        if not isinstance(value.get("stdout_tail"), str) or not isinstance(
            value.get("stderr_tail"), str
        ):
            reasons.append("captured output")
        if (
            not valid_hash_rows(value.get("expected_outputs"), require_fresh=True)
            or value.get("expected_outputs") != expected_output_evidence
        ):
            reasons.append("output evidence")
        for field, label in (
            ("project_output_mismatches", "project output mismatches"),
            ("unexpected_outputs", "unexpected outputs"),
            ("unexpected_workspace_files", "unexpected workspace files"),
            ("runtime_input_drift", "runtime input drift"),
            ("solve_blockers", "solve blockers"),
        ):
            if not isinstance(value.get(field), list) or value.get(field):
                reasons.append(label)
        if value.get("run_manifest_sha256") != current_run_sha256:
            reasons.append("run manifest drift")
        if not isinstance(value.get("freeze_details"), dict):
            reasons.append("freeze details")
        if value.get("freeze_checked") is True:
            if value.get("freeze_valid") is not True:
                reasons.append("freeze invalid")
            if value.get("frozen_manifest_sha256") != current_freeze_sha256:
                reasons.append("freeze manifest drift")
        elif value.get("freeze_checked") is False:
            if value.get("frozen_manifest_sha256") is not None:
                reasons.append("unexpected freeze hash")
        else:
            reasons.append("freeze checked type")
        if require_current_freeze:
            if value.get("freeze_checked") is not True or value.get(
                "freeze_valid"
            ) is not True:
                reasons.append("freeze not verified")
            if value.get("frozen_manifest_sha256") != current_freeze_sha256:
                reasons.append("freeze manifest drift")
            for item in expected_output_evidence:
                frozen_item = frozen_output_map.get(item["path"])
                if (
                    not frozen_item
                    or frozen_item.get("size") != item["size"]
                    or frozen_item.get("sha256") != item["sha256"]
                ):
                    reasons.append(f"output not bound to freeze: {item['path']}")
        if value.get("engine_sha256") != current_engine_sha256:
            reasons.append("engine drift")
        if value.get("report_path") != relative_report:
            reasons.append("report path")
        report_body = dict(value)
        supplied_report_sha256 = report_body.pop("report_sha256", None)
        calculated_report_sha256 = hashlib.sha256(
            canonical_json(report_body)
        ).hexdigest()
        if supplied_report_sha256 != calculated_report_sha256:
            reasons.append("report self hash")
        if reasons:
            rejected[relative_report] = sorted(set(reasons))
        else:
            passing.append(relative_report)
    return passing, rejected


def manual_replay_report_evidence(
    root: Path, *, require_current_freeze: bool
) -> tuple[list[str], dict[str, list[str]]]:
    run_path = root / "state" / "run_manifest.json"
    freeze_path = root / "state" / "frozen_manifest.json"
    raw_run = read_json_or(run_path, {})
    run = raw_run if isinstance(raw_run, dict) else {}
    declared_inputs, input_errors = validate_declared_paths(
        root,
        run.get("declared_inputs"),
        "declared_inputs",
        RUNTIME_INPUT_BASES,
        require_files=True,
    )
    official_inputs, official_errors = validate_official_attachment_inputs(
        root, run.get("official_attachment_inputs"), declared_inputs
    )
    declared_outputs, output_errors = validate_declared_paths(
        root,
        run.get("expected_outputs"),
        "expected_outputs",
        RUNTIME_OUTPUT_BASES,
        require_files=True,
    )
    runtime_paths = list(iter_evidence_files(root / "work" / "code"))
    runtime_paths.extend(
        path
        for value in declared_inputs
        if (path := safe_project_path(root, value)).is_file()
    )
    runtime_map = {relative_posix(root, path): path for path in runtime_paths}
    expected_runtime_files = sorted(runtime_map)
    expected_runtime_evidence = build_hash_manifest(root, runtime_map.values())
    expected_output_evidence = (
        build_hash_manifest(
            root, [safe_project_path(root, value) for value in declared_outputs]
        )
        if not output_errors
        else []
    )
    current_run_hash = sha256_file(run_path) if run_path.is_file() else ""
    freeze_exists = freeze_path.is_file()
    current_freeze_hash = sha256_file(freeze_path) if freeze_exists else ""
    freeze_valid = verify_freeze(root)[0] if freeze_exists else False
    current_engine_hash = sha256_file(Path(__file__).resolve())
    config = read_json_or(root / "cumcm-project.json", {})
    competition_mode = isinstance(config, dict) and config.get("mode") == "competition"
    required_fields = {
        "schema_version",
        "recorded_at",
        "performed_by",
        "workspace_description",
        "notes",
        "procedure",
        "declared_entrypoint",
        "environment",
        "isolated_workspace",
        "inputs_unchanged",
        "outputs_regenerated",
        "runtime_files",
        "runtime_evidence",
        "declared_inputs",
        "official_attachment_inputs",
        "expected_outputs",
        "run_manifest_sha256",
        "frozen_manifest_sha256",
        "freeze_checked",
        "freeze_valid",
        "engine_sha256",
        "outcome",
        "report_path",
        "report_sha256",
    }
    contract_errors = input_errors + official_errors + output_errors
    if run.get("program_usage") != "interactive":
        contract_errors.append("program_usage")
    passing: list[str] = []
    rejected: dict[str, list[str]] = {}
    for report_path in sorted((root / "reports").glob("manual_replay_*.json")):
        relative_report = relative_posix(root, report_path)
        raw_value = read_json_or(report_path, {})
        value = raw_value if isinstance(raw_value, dict) else {}
        reasons: list[str] = []
        if set(value) != required_fields:
            reasons.append("report fields")
        if contract_errors:
            reasons.append("current run contract invalid")
        if not current_schema(value.get("schema_version")):
            reasons.append("schema version")
        if not valid_iso_timestamp(value.get("recorded_at")):
            reasons.append("recorded_at")
        if not nonempty_text(value.get("performed_by")) or (
            competition_mode and reserved_approver(value.get("performed_by", ""))
        ):
            reasons.append("performed_by")
        if not nonempty_text(value.get("workspace_description")) or len(
            value.get("workspace_description", "").strip()
        ) < 12:
            reasons.append("workspace description")
        if not nonempty_text(value.get("notes")) or len(value.get("notes", "").strip()) < 12:
            reasons.append("notes")
        if value.get("procedure") != run.get("manual_replay_procedure") or not substantive_manual_procedure(
            value.get("procedure")
        ):
            reasons.append("procedure")
        if value.get("declared_entrypoint") != run.get("entrypoint"):
            reasons.append("entrypoint")
        if value.get("environment") != run.get("environment"):
            reasons.append("environment")
        if value.get("isolated_workspace") is not True:
            reasons.append("isolated workspace")
        if value.get("inputs_unchanged") is not True:
            reasons.append("inputs unchanged")
        if value.get("outputs_regenerated") is not True:
            reasons.append("outputs regenerated")
        if value.get("runtime_files") != expected_runtime_files:
            reasons.append("runtime files")
        if value.get("runtime_evidence") != expected_runtime_evidence:
            reasons.append("runtime evidence")
        if value.get("declared_inputs") != declared_inputs:
            reasons.append("declared inputs")
        if value.get("official_attachment_inputs") != official_inputs:
            reasons.append("official attachment inputs")
        if value.get("expected_outputs") != expected_output_evidence:
            reasons.append("expected outputs")
        if value.get("run_manifest_sha256") != current_run_hash:
            reasons.append("run manifest drift")
        if value.get("frozen_manifest_sha256") != current_freeze_hash:
            reasons.append("freeze manifest drift")
        if value.get("freeze_checked") is not freeze_exists:
            reasons.append("freeze checked")
        if value.get("freeze_valid") is not freeze_valid:
            reasons.append("freeze validity")
        if require_current_freeze and (not freeze_exists or not freeze_valid):
            reasons.append("current freeze required")
        if value.get("engine_sha256") != current_engine_hash:
            reasons.append("engine drift")
        if value.get("outcome") != "PASS":
            reasons.append("outcome")
        if value.get("report_path") != relative_report:
            reasons.append("report path")
        body = dict(value)
        stored_hash = body.pop("report_sha256", None)
        if not isinstance(stored_hash, str) or stored_hash != hashlib.sha256(
            canonical_json(body)
        ).hexdigest():
            reasons.append("report hash")
        if reasons:
            rejected[relative_report] = sorted(set(reasons))
        else:
            passing.append(relative_report)
    return passing, rejected


def audit_intake(root: Path, findings: list[dict[str, Any]]) -> None:
    raw_config = read_json_or(root / "cumcm-project.json", {})
    config = raw_config if isinstance(raw_config, dict) else {}
    valid_config = (
        current_schema(config.get("schema_version"))
        and config.get("competition") == "CUMCM"
        and isinstance(config.get("year"), int)
        and not isinstance(config.get("year"), bool)
        and config.get("mode") in {"competition", "training"}
    )
    add_finding(
        findings,
        "INTAKE-001",
        "project_required",
        valid_config,
        "项目元数据完整" if valid_config else "项目元数据缺失或不合法",
        config,
        "修正 cumcm-project.json 的竞赛、年份、模式和 schema。",
    )

    raw_rules = read_json_or(root / "state" / "rules_manifest.json", {})
    rules = raw_rules if isinstance(raw_rules, dict) else {}
    sources = rules.get("sources", [])
    if not isinstance(sources, list):
        sources = []
    source_ids = [
        source.get("id") for source in sources if isinstance(source, dict)
    ]
    source_by_id = {
        source.get("id"): source
        for source in sources
        if isinstance(source, dict) and nonempty_text(source.get("id"))
    }
    required_sources = (
        {item["id"]: item["url"] for item in OFFICIAL_2026_SOURCES}
        if config.get("year") == 2026
        else {}
    )
    missing_required_sources = sorted(set(required_sources) - set(source_by_id))
    url_mismatches = sorted(
        source_id
        for source_id, expected_url in required_sources.items()
        if source_id in source_by_id
        and source_by_id[source_id].get("url") != expected_url
    )
    rules_verified = (
        current_schema(rules.get("schema_version"))
        and rules.get("competition") == "CUMCM"
        and isinstance(rules.get("year"), int)
        and not isinstance(rules.get("year"), bool)
        and rules.get("year") == config.get("year")
        and valid_iso_timestamp(rules.get("verified_at"))
        and nonempty_text(rules.get("verified_by"))
        and isinstance(rules.get("confirmed_for_year"), int)
        and not isinstance(rules.get("confirmed_for_year"), bool)
        and rules.get("confirmed_for_year") == config.get("year")
        and bool(sources)
        and len(source_ids) == len(set(source_ids))
        and not missing_required_sources
        and not url_mismatches
        and isinstance(rules.get("region_rules"), list)
        and isinstance(rules.get("classification"), dict)
        and set(rules.get("classification", {}))
        == {"official_hard", "project_required", "quality_advisory"}
        and all(nonempty_text(value) for value in rules.get("classification", {}).values())
        and nonempty_text(rules.get("notes"))
        and all(
            isinstance(source, dict)
            and nonempty_text(source.get("id"))
            and nonempty_text(source.get("title"))
            and source.get("status") == "verified"
            and nonempty_text(source.get("url"))
            for source in sources
        )
    )
    add_finding(
        findings,
        "RULES-001",
        "project_required",
        rules_verified,
        "当届规则来源已逐项核验" if rules_verified else "当届规则尚未完成来源核验",
        {
            "verified_at": rules.get("verified_at"),
            "verified_by": rules.get("verified_by"),
            "sources": sources,
            "missing_required_sources": missing_required_sources,
            "url_mismatches": url_mismatches,
            "manifest_type": type(raw_rules).__name__,
        },
        "打开当届全国/赛区官方文件，更新来源状态、核验时间和适用年份。",
    )

    raw_problem = read_json_or(root / "state" / "problem_contract.json", {})
    problem = raw_problem if isinstance(raw_problem, dict) else {}
    questions = problem.get("questions", [])
    question_shape = bool(questions) and all(
        isinstance(item, dict)
        and nonempty_text(item.get("id"))
        and nonempty_text(item.get("task"))
        and nonempty_text(item.get("output"))
        and isinstance(item.get("inputs"), list)
        and all(nonempty_text(value) for value in item.get("inputs", []))
        and isinstance(item.get("depends_on"), list)
        and all(nonempty_text(value) for value in item.get("depends_on", []))
        for item in questions
    )
    ids = [item.get("id") for item in questions if isinstance(item, dict)]
    dependency_errors: list[str] = []
    graph: dict[str, list[str]] = {}
    for item in questions:
        if not isinstance(item, dict) or not nonempty_text(item.get("id")):
            continue
        question_id = item["id"]
        dependencies = item.get("depends_on", [])
        if not isinstance(dependencies, list):
            continue
        graph[question_id] = [value for value in dependencies if isinstance(value, str)]
        for dependency in dependencies:
            if dependency == question_id:
                dependency_errors.append(f"{question_id} 自依赖")
            elif dependency not in ids:
                dependency_errors.append(f"{question_id} 依赖未知问题 {dependency}")

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(question_id: str) -> None:
        if question_id in visiting:
            dependency_errors.append(f"问题依赖存在环: {question_id}")
            return
        if question_id in visited:
            return
        visiting.add(question_id)
        for dependency in graph.get(question_id, []):
            if dependency in graph:
                visit(dependency)
        visiting.remove(question_id)
        visited.add(question_id)

    for question_id in graph:
        visit(question_id)
    data_inventory, data_inventory_errors, self_sourced_paths = validate_data_inventory(
        root, problem.get("data_inventory")
    )
    problem_ok = (
        current_schema(problem.get("schema_version"))
        and nonempty_text(problem.get("problem_code"))
        and nonempty_text(problem.get("problem_title"))
        and nonempty_text(problem.get("problem_group"))
        and question_shape
        and len(ids) == len(set(ids))
        and not dependency_errors
        and isinstance(problem.get("data_inventory"), list)
        and not data_inventory_errors
        and isinstance(problem.get("unknowns"), list)
        and isinstance(problem.get("assumptions_to_test"), list)
        and isinstance(problem.get("risk_register"), list)
        and bool(problem.get("risk_register"))
        and all(
            nonempty_text(item) or (isinstance(item, dict) and bool(item))
            for item in problem.get("risk_register", [])
        )
    )
    add_finding(
        findings,
        "INTAKE-002",
        "project_required",
        problem_ok,
        "问题合同覆盖题目和问题 ID" if problem_ok else "问题合同不完整或问题 ID 重复",
        {
            "problem_code": problem.get("problem_code"),
            "question_ids": ids,
            "dependency_errors": dependency_errors,
            "data_inventory": data_inventory,
            "data_inventory_errors": data_inventory_errors,
            "self_sourced_used_paths": self_sourced_paths,
        },
        "补齐 problem_code/title、每问 task/output、数据清单和风险表。",
    )
    gate_ok = gate_is_approved(root, "problem_selection")
    add_finding(
        findings,
        "GATE-G0",
        "project_required",
        gate_ok,
        "G0 选题已由团队批准" if gate_ok else "G0 选题尚未由团队批准",
        gate_data(root).get("gates", {}).get("problem_selection"),
        "团队确认题意与选题后记录 problem_selection 门禁。",
    )


def audit_design(root: Path, findings: list[dict[str, Any]]) -> None:
    ids = question_ids(root)
    model = read_json_or(root / "state" / "model_contract.json", {})
    contracts = model.get("questions", {}) if isinstance(model, dict) else {}
    global_dependencies = (
        model.get("global_dependencies") if isinstance(model, dict) else None
    )
    missing: list[str] = []
    invalid: list[str] = []
    for question_id in ids:
        contract = contracts.get(question_id) if isinstance(contracts, dict) else None
        if not isinstance(contract, dict):
            missing.append(question_id)
            continue
        required_text = ("baseline", "main_model", "fallback")
        assumptions = contract.get("assumptions")
        validation = contract.get("validation")
        if (
            not all(nonempty_text(contract.get(key)) for key in required_text)
            or not isinstance(assumptions, list)
            or not assumptions
            or not all(nonempty_text(item) for item in assumptions)
            or not isinstance(validation, list)
            or not validation
            or not all(nonempty_text(item) for item in validation)
        ):
            invalid.append(question_id)
    contracts_ok = (
        isinstance(model, dict)
        and current_schema(model.get("schema_version"))
        and isinstance(global_dependencies, list)
        and all(
            nonempty_text(item) or (isinstance(item, dict) and bool(item))
            for item in global_dependencies
        )
        and bool(ids)
        and not missing
        and not invalid
    )
    add_finding(
        findings,
        "DESIGN-001",
        "project_required",
        contracts_ok,
        "每问已有 baseline/main/fallback 与验证计划"
        if contracts_ok
        else "模型合同缺项",
        {
            "missing": missing,
            "invalid": invalid,
            "global_dependencies_type": type(global_dependencies).__name__,
        },
        "按问题 ID 补齐基线、主模型、退路、假设和题型适配验证。",
    )

    chain_ok, chain_errors, decisions = verify_event_chain(
        root / "state" / "decision_ledger.jsonl"
    )
    raw_config = read_json_or(root / "cumcm-project.json", {})
    config = raw_config if isinstance(raw_config, dict) else {}
    invalid_decisions: dict[int, list[str]] = {}
    for index, item in enumerate(decisions):
        event_errors: list[str] = []
        if item.get("event_type") != "decision":
            event_errors.append("event_type")
        if item.get("question_id") not in ids:
            event_errors.append("question_id")
        if not all(
            nonempty_text(item.get(field))
            for field in (
                "choice",
                "alternatives",
                "evidence",
                "impact",
                "decided_by",
            )
        ):
            event_errors.append("required_text")
        affects_stage = item.get("affects_stage")
        if affects_stage not in AFFECTS_GATE:
            event_errors.append("affects_stage")
        elif item.get("invalidates_from") != AFFECTS_GATE[affects_stage]:
            event_errors.append("invalidates_from")
        if config.get("mode") == "competition" and reserved_approver(
            str(item.get("decided_by", ""))
        ):
            event_errors.append("competition decided_by")
        if event_errors:
            invalid_decisions[index] = event_errors
    covered = {
        item.get("question_id")
        for item in decisions
        if item.get("question_id") in ids
    }
    ledger_ok = (
        chain_ok
        and bool(decisions)
        and not invalid_decisions
        and set(ids).issubset(covered)
    )
    add_finding(
        findings,
        "DESIGN-002",
        "project_required",
        ledger_ok,
        "决策账本完整且哈希链有效" if ledger_ok else "决策账本损坏或未覆盖全部问题",
        {
            "errors": chain_errors,
            "invalid_events": invalid_decisions,
            "covered": sorted(covered),
        },
        "使用 record-decision 为每问记录选择、备选和证据；不要手改历史行。",
    )
    gate_ok = gate_is_approved(root, "model_contract")
    add_finding(
        findings,
        "GATE-G1",
        "project_required",
        gate_ok,
        "G1 模型合同已由团队批准" if gate_ok else "G1 模型合同尚未由团队批准",
        gate_data(root).get("gates", {}).get("model_contract"),
        "团队审阅公式、假设、退路和验证计划后批准 model_contract。",
    )


def audit_solve(
    root: Path, findings: list[dict[str, Any]], *, require_replay: bool = True
) -> None:
    raw_run = read_json_or(root / "state" / "run_manifest.json", {})
    run = raw_run if isinstance(raw_run, dict) else {}
    program_usage = run.get("program_usage")
    all_code_artifacts = list(iter_evidence_files(root / "work" / "code"))
    code_files = [
        path
        for path in all_code_artifacts
        if path.suffix.casefold() in CODE_SUFFIXES
    ]
    if program_usage in {"code", "interactive"}:
        artifact_ok = bool(all_code_artifacts)
        artifact_message = (
            "存在可提交的代码或软件交互工件"
            if artifact_ok
            else "声明使用程序/交互软件，但 work/code 中没有工件"
        )
    elif program_usage == "none":
        artifact_ok = not all_code_artifacts and nonempty_text(run.get("no_program_reason"))
        artifact_message = (
            "已明确记录未使用程序及原因"
            if artifact_ok
            else "未使用程序的声明与工件或理由不一致"
        )
    else:
        artifact_ok = False
        artifact_message = "program_usage 尚未确定"
    add_finding(
        findings,
        "SOLVE-001",
        "project_required",
        artifact_ok,
        artifact_message,
        {
            "program_usage": program_usage,
            "recognized_artifacts": [relative_posix(root, path) for path in code_files],
            "all_artifacts": [relative_posix(root, path) for path in all_code_artifacts],
            "no_program_reason": run.get("no_program_reason"),
        },
        "将 program_usage 设为 code/interactive/none；前两者提交完整工件，none 必须说明原因且不留程序工件。",
    )

    required_run_keys = {
        "schema_version",
        "program_usage",
        "entrypoint",
        "command",
        "environment",
        "randomness",
        "declared_inputs",
        "official_attachment_inputs",
        "expected_outputs",
        "manual_replay_procedure",
        "no_program_reason",
    }
    missing_run_keys = sorted(required_run_keys - set(run))
    entrypoint = run.get("entrypoint", "")
    entry_ok = False
    entry_error = ""
    entry_path: Path | None = None
    if nonempty_text(entrypoint):
        try:
            entry_path = safe_project_path(root, entrypoint)
            entry_ok = entry_path.is_file() and path_under_any(
                root, entry_path, ("work/code",)
            )
            if entry_path.is_file() and not entry_ok:
                entry_error = "入口必须位于 work/code/"
            elif entry_ok and program_usage == "interactive":
                entry_ok, entry_error = interactive_artifact_ok(entry_path)
        except EngineError as exc:
            entry_error = str(exc)
    raw_expected_outputs = run.get("expected_outputs")
    expected_outputs = raw_expected_outputs if isinstance(raw_expected_outputs, list) else []
    normalized_outputs, output_errors = validate_declared_paths(
        root,
        raw_expected_outputs,
        "expected_outputs",
        RUNTIME_OUTPUT_BASES,
        require_files=True,
    )
    if program_usage in {"code", "interactive"} and not expected_outputs:
        output_errors.append("expected_outputs 为空")
    elif program_usage == "none" and expected_outputs:
        output_errors.append("none 模式的 expected_outputs 必须为空列表")
    managed_output_files = list(iter_evidence_files(root / "work" / "results")) + list(
        iter_evidence_files(root / "work" / "figures")
    )
    managed_output_names = {
        relative_posix(root, path) for path in managed_output_files
    }
    undeclared_output_artifacts = sorted(
        managed_output_names - set(normalized_outputs)
    )
    if program_usage in {"code", "interactive"} and undeclared_output_artifacts:
        output_errors.append(
            "work/results 或 work/figures 含未声明输出: "
            + ", ".join(undeclared_output_artifacts)
        )
    normalized_inputs, input_errors = validate_declared_paths(
        root,
        run.get("declared_inputs"),
        "declared_inputs",
        RUNTIME_INPUT_BASES,
        require_files=True,
    )
    official_inputs, official_input_errors = validate_official_attachment_inputs(
        root, run.get("official_attachment_inputs"), normalized_inputs
    )
    input_errors.extend(official_input_errors)
    if set(normalized_inputs) & set(normalized_outputs):
        input_errors.append("declared_inputs 与 expected_outputs 不得重叠")
    command_errors: list[str] = []
    if program_usage == "code":
        _, command_errors = command_contract_errors(
            root, run, normalized_inputs, normalized_outputs
        )
    randomness = run.get("randomness")
    randomness_ok = (
        isinstance(randomness, dict)
        and randomness.get("mode") in {"deterministic", "seeded", "not_applicable"}
        and isinstance(randomness.get("seeds"), list)
        and (randomness.get("mode") != "seeded" or bool(randomness.get("seeds")))
    )
    environment = run.get("environment")
    environment_ok = valid_environment(environment, program_usage)
    common_run_ok = (
        current_schema(run.get("schema_version"))
        and not missing_run_keys
        and environment_ok
        and randomness_ok
        and not output_errors
        and not input_errors
    )
    if program_usage == "code":
        run_ok = (
            common_run_ok
            and entry_ok
            and not command_errors
            and run.get("manual_replay_procedure") == ""
            and run.get("no_program_reason") == ""
        )
    elif program_usage == "interactive":
        run_ok = (
            common_run_ok
            and entry_ok
            and run.get("command") == ""
            and substantive_manual_procedure(run.get("manual_replay_procedure"))
            and run.get("no_program_reason") == ""
        )
    elif program_usage == "none":
        run_ok = (
            common_run_ok
            and nonempty_text(run.get("no_program_reason"))
            and run.get("entrypoint") == ""
            and run.get("command") == ""
            and run.get("manual_replay_procedure") == ""
            and run.get("declared_inputs") == []
            and run.get("official_attachment_inputs") == []
            and run.get("expected_outputs") == []
            and run.get("environment") == {}
            and randomness == {"mode": "not_applicable", "seeds": []}
        )
    else:
        run_ok = False
    add_finding(
        findings,
        "SOLVE-002",
        "project_required",
        run_ok,
        "统一运行入口、环境和随机性已登记" if run_ok else "运行清单不完整或入口不可用",
        {
            "entrypoint": entrypoint,
            "error": entry_error,
            "missing_keys": missing_run_keys,
            "input_errors": input_errors,
            "output_errors": output_errors,
            "official_attachment_inputs": official_inputs,
            "undeclared_output_artifacts": undeclared_output_artifacts,
            "command_errors": command_errors,
            "run_manifest": run,
        },
        "代码模式登记相对入口/命令；交互模式登记工作簿或命令文件和人工重放步骤；无程序模式说明原因。",
    )

    result_files = managed_output_files
    ledger = read_json_or(root / "state" / "result_ledger.json", {})
    results = ledger.get("results", []) if isinstance(ledger, dict) else []
    ids = question_ids(root)
    result_ids: list[str] = []
    covered: set[str] = set()
    invalid: list[int] = []
    expected_output_names = set(normalized_outputs)
    for index, item in enumerate(results):
        if not isinstance(item, dict):
            invalid.append(index)
            continue
        result_ids.append(str(item.get("id", "")))
        if item.get("question_id") in ids:
            covered.add(item["question_id"])
        required_text = ("id", "question_id", "name", "unit")
        context_fields = ("data_scope", "parameter_set", "random_seed")
        precision = item.get("precision")
        provenance_fields = (
            item.get("source_file"),
            item.get("source_object"),
            item.get("generation_command"),
        )
        row_invalid = (
            not all(nonempty_text(item.get(key)) for key in required_text)
            or item.get("question_id") not in ids
            or not all(nonempty_text(item.get(key)) for key in context_fields)
            or "value" not in item
            or not meaningful_json_value(item.get("value"))
            or not (
                positive_finite_number(precision)
                or nonempty_text(precision)
            )
            or not nonempty_text(item.get("verification_status"))
            or not any(nonempty_text(value) for value in provenance_fields)
        )
        if program_usage in {"code", "interactive"}:
            source_name = str(item.get("source_file", "")).replace("\\", "/")
            row_invalid = (
                row_invalid
                or not nonempty_text(item.get("source_file"))
                or source_name not in expected_output_names
            )
        if nonempty_text(item.get("source_file")):
            try:
                source_path = safe_project_path(root, item["source_file"])
                row_invalid = (
                    row_invalid
                    or not source_path.is_file()
                    or is_ephemeral_file(source_path)
                    or not path_under_any(
                        root,
                        source_path,
                        RUNTIME_OUTPUT_BASES,
                    )
                )
            except EngineError:
                row_invalid = True
        if row_invalid:
            invalid.append(index)
    result_file_required = program_usage in {"code", "interactive"} or any(
        isinstance(item, dict) and nonempty_text(item.get("source_file"))
        for item in results
    )
    ledger_ok = (
        isinstance(ledger, dict)
        and current_schema(ledger.get("schema_version"))
        and (bool(result_files) or not result_file_required)
        and bool(results)
        and not invalid
        and len(result_ids) == len(set(result_ids))
        and set(ids).issubset(covered)
    )
    add_finding(
        findings,
        "SOLVE-003",
        "project_required",
        ledger_ok,
        "结果文件与结果账本覆盖全部问题" if ledger_ok else "结果账本缺失、重复或未覆盖全部问题",
        {
            "result_files": [relative_posix(root, path) for path in result_files],
            "invalid_rows": invalid,
            "covered_questions": sorted(covered),
        },
        "登记每个关键结果的 ID、问题、值、单位、精度、数据/参数/随机性、来源和验证状态。",
    )

    if program_usage == "code":
        passing_replays, rejected_replays = replay_report_evidence(
            root, require_current_freeze=False
        )
        replay_ok = bool(passing_replays) if require_replay else True
        replay_status = "pass" if replay_ok else "fail"
    elif program_usage == "interactive":
        passing_replays, rejected_replays = manual_replay_report_evidence(
            root, require_current_freeze=False
        )
        replay_ok = bool(passing_replays) if require_replay else True
        replay_status = "pass" if replay_ok else "fail"
    elif program_usage == "none":
        replay_ok = True
        replay_status = "not_applicable"
        passing_replays, rejected_replays = [], {}
    else:
        replay_ok = False
        replay_status = "fail"
        passing_replays, rejected_replays = [], {}
    add_finding(
        findings,
        "SOLVE-004",
        "project_required",
        replay_ok,
        (
            "代码已在洁净副本中完成预冻结重放"
            if replay_status == "pass" and program_usage == "code"
            else (
                "交互重放步骤已登记"
                if replay_status == "pass"
                else (
                    "未使用程序，重放不适用"
                    if replay_status == "not_applicable"
                    else "求解阶段缺少有效的洁净重放证据"
                )
            )
        ),
        {
            "program_usage": program_usage,
            "passing_reports": passing_replays,
            "rejected_reports": rejected_replays,
            "internal_replay_validation": not require_replay,
        },
        "代码模式先运行 replay，再批准 G2；冻结后需再次 replay 供最终交付核验。",
        status=replay_status,
    )


def frozen_scope(root: Path) -> list[Path]:
    files: list[Path] = []
    config = root / "cumcm-project.json"
    if config.is_file():
        files.append(config)
    for relative in (
        "work/intake",
        "work/modeling",
        "work/code",
        "work/results",
        "work/figures",
    ):
        files.extend(iter_evidence_files(root / relative))
    for relative in (
        "state/rules_manifest.json",
        "state/problem_contract.json",
        "state/model_contract.json",
        "state/decision_ledger.jsonl",
        "state/run_manifest.json",
        "state/result_ledger.json",
        "state/verification_report.json",
    ):
        path = root / relative
        if path.is_file():
            files.append(path)
    unique = {relative_posix(root, path): path for path in files}
    return [unique[key] for key in sorted(unique, key=str.casefold)]


def build_hash_manifest(root: Path, files: Iterable[Path]) -> list[dict[str, Any]]:
    return [
        {
            "path": relative_posix(root, path),
            "size": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for path in files
    ]


def valid_hash_manifest_rows(raw: Any) -> bool:
    if not isinstance(raw, list):
        return False
    paths: list[str] = []
    for item in raw:
        if (
            not isinstance(item, dict)
            or set(item) != {"path", "size", "sha256"}
            or not nonempty_text(item.get("path"))
            or not isinstance(item.get("size"), int)
            or isinstance(item.get("size"), bool)
            or item.get("size", -1) < 0
            or not re.fullmatch(r"[0-9a-f]{64}", str(item.get("sha256", "")))
        ):
            return False
        paths.append(item["path"])
    return len(paths) == len(set(paths))


def verify_freeze(root: Path) -> tuple[bool, dict[str, Any]]:
    path = root / "state" / "frozen_manifest.json"
    if not path.exists():
        return False, {"error": "missing frozen_manifest.json"}
    manifest = read_json(path)
    expected_items = manifest.get("files", []) if isinstance(manifest, dict) else []
    if not isinstance(expected_items, list):
        expected_items = []
    expected = {
        item.get("path"): item
        for item in expected_items
        if isinstance(item, dict) and nonempty_text(item.get("path"))
    }
    expected_keys = {
        "schema_version",
        "created_at",
        "algorithm",
        "files",
        "manifest_sha256",
    }
    created_at_valid = False
    if isinstance(manifest, dict) and nonempty_text(manifest.get("created_at")):
        try:
            created_at_valid = (
                datetime.fromisoformat(
                    manifest["created_at"].replace("Z", "+00:00")
                ).tzinfo
                is not None
            )
        except (TypeError, ValueError):
            created_at_valid = False
    manifest_well_formed = (
        isinstance(manifest, dict)
        and set(manifest) == expected_keys
        and valid_hash_manifest_rows(expected_items)
        and len(expected) == len(expected_items)
        and manifest.get("algorithm") == "sha256"
        and created_at_valid
    )
    schema_valid = (
        isinstance(manifest, dict)
        and current_schema(manifest.get("schema_version"))
    )
    manifest_hash_valid = (
        isinstance(manifest, dict)
        and manifest.get("manifest_sha256")
        == hashlib.sha256(
            canonical_json(
                {key: value for key, value in manifest.items() if key != "manifest_sha256"}
            )
        ).hexdigest()
    )
    current_items = build_hash_manifest(root, frozen_scope(root))
    current = {item["path"]: item for item in current_items}
    missing = sorted(set(expected) - set(current))
    added = sorted(set(current) - set(expected))
    changed = sorted(
        path_name
        for path_name in set(expected) & set(current)
        if expected[path_name].get("sha256") != current[path_name].get("sha256")
        or expected[path_name].get("size") != current[path_name].get("size")
    )
    ok = (
        bool(expected)
        and schema_valid
        and manifest_well_formed
        and manifest_hash_valid
        and not missing
        and not added
        and not changed
    )
    return ok, {
        "missing": missing,
        "added": added,
        "changed": changed,
        "manifest_well_formed": manifest_well_formed,
        "schema_valid": schema_valid,
        "manifest_hash_valid": manifest_hash_valid,
    }


def final_lock_scope(root: Path) -> list[Path]:
    """Return the complete evidence pack whose drift invalidates final delivery."""
    files: list[Path] = []
    config = root / "cumcm-project.json"
    if config.is_file():
        files.append(config)
    for relative in ("state", "work", "paper", "supporting", "delivery"):
        files.extend(iter_evidence_files(root / relative))
    reports = root / "reports"
    if reports.exists():
        files.extend(path for path in reports.glob("audit_*.json") if path.is_file())
        files.extend(path for path in reports.glob("replay_*.json") if path.is_file())
        files.extend(path for path in reports.glob("manual_replay_*.json") if path.is_file())
    unique = {relative_posix(root, path): path for path in files}
    return [unique[key] for key in sorted(unique, key=str.casefold)]


def audit_verify(root: Path, findings: list[dict[str, Any]]) -> None:
    report = read_json_or(root / "state" / "verification_report.json", {})
    questions = report.get("questions", {}) if isinstance(report, dict) else {}
    ids = question_ids(root)
    missing: list[str] = []
    invalid: dict[str, list[str]] = {}
    required_groups = {
        "dimension_or_unit",
        "boundary_or_invariant",
        "independent_evidence",
        "uncertainty_or_robustness",
    }
    for question_id in ids:
        item = questions.get(question_id) if isinstance(questions, dict) else None
        if not isinstance(item, dict):
            missing.append(question_id)
            continue
        checks = item.get("checks", [])
        valid_groups: set[str] = set()
        bad: list[str] = []
        if not isinstance(checks, list):
            bad.append("checks")
        else:
            for check in checks:
                if not isinstance(check, dict):
                    continue
                check_type = check.get("type")
                status = check.get("status")
                evidence = check.get("evidence")
                rationale = check.get("rationale")
                if check_type in required_groups and (
                    (status == "pass" and nonempty_text(evidence))
                    or (status == "not_applicable" and nonempty_text(rationale))
                ):
                    valid_groups.add(check_type)
            bad.extend(sorted(required_groups - valid_groups))
        if bad:
            invalid[question_id] = bad
    verification_ok = (
        isinstance(report, dict)
        and current_schema(report.get("schema_version"))
        and bool(ids)
        and not missing
        and not invalid
    )
    add_finding(
        findings,
        "VERIFY-001",
        "project_required",
        verification_ok,
        "验证报告覆盖每问的核心证据类别" if verification_ok else "验证报告缺少核心证据类别",
        {"missing": missing, "invalid": invalid},
        "按题型完成量纲/单位、边界/不变量、独立证据和不确定性/稳健性；不适用时说明理由。",
    )

    ledger = read_json_or(root / "state" / "result_ledger.json", {})
    results = ledger.get("results", []) if isinstance(ledger, dict) else []
    ledger_verified = (
        isinstance(ledger, dict)
        and current_schema(ledger.get("schema_version"))
        and bool(results)
        and all(
            isinstance(item, dict) and item.get("verification_status") == "verified"
            for item in results
        )
    )
    add_finding(
        findings,
        "VERIFY-002",
        "project_required",
        ledger_verified,
        "结果账本条目均已验证" if ledger_verified else "仍有结果未标为 verified",
        [
            item.get("id")
            for item in results
            if isinstance(item, dict) and item.get("verification_status") != "verified"
        ],
        "完成相应验证后再更新 verification_status。",
    )

    gate_ok = gate_is_approved(root, "result_freeze")
    add_finding(
        findings,
        "GATE-G2",
        "project_required",
        gate_ok,
        "G2 结果已由团队批准" if gate_ok else "G2 结果尚未由团队批准",
        gate_data(root).get("gates", {}).get("result_freeze"),
        "团队核对关键结果和验证报告后批准 result_freeze。",
    )
    freeze_ok, freeze_details = verify_freeze(root)
    add_finding(
        findings,
        "FREEZE-001",
        "project_required",
        freeze_ok,
        "冻结清单有效且无漂移" if freeze_ok else "缺少冻结清单或冻结范围已漂移",
        freeze_details,
        "若尚未冻结则运行 freeze；若有证据变化则先 reopen、重算、重审再冻结。",
    )


def audit_write(root: Path, findings: list[dict[str, Any]]) -> None:
    paper_files = [
        path
        for path in iter_evidence_files(root / "paper")
        if path.suffix.casefold() in PAPER_SUFFIXES
    ]
    add_finding(
        findings,
        "WRITE-001",
        "project_required",
        bool(paper_files) and all(path.stat().st_size > 0 for path in paper_files),
        "存在非空论文源稿或渲染稿"
        if paper_files and all(path.stat().st_size > 0 for path in paper_files)
        else "paper 目录中没有非空论文文件",
        [
            {"path": relative_posix(root, path), "size": path.stat().st_size}
            for path in paper_files
        ],
        "生成非空、可审阅的论文源稿或 Word/PDF。",
    )

    mapping = read_json_or(root / "state" / "claim_evidence.json", {})
    claims = mapping.get("claims", []) if isinstance(mapping, dict) else []
    ledger = read_json_or(root / "state" / "result_ledger.json", {})
    result_ids = {
        item.get("id")
        for item in (ledger.get("results", []) if isinstance(ledger, dict) else [])
        if isinstance(item, dict) and nonempty_text(item.get("id"))
    }
    invalid: dict[int, list[str]] = {}
    claim_ids: list[str] = []
    for index, claim in enumerate(claims):
        problems: list[str] = []
        if (
            not isinstance(claim, dict)
            or not nonempty_text(claim.get("id"))
            or not nonempty_text(claim.get("claim"))
            or not isinstance(claim.get("evidence"), list)
            or not claim.get("evidence")
        ):
            invalid[index] = ["claim shape"]
            continue
        claim_ids.append(claim["id"])
        for evidence in claim["evidence"]:
            if not isinstance(evidence, dict):
                problems.append("evidence must be an object")
                continue
            evidence_type = evidence.get("type")
            reference = evidence.get("ref")
            if evidence_type == "result":
                if reference not in result_ids:
                    problems.append(f"unknown result: {reference}")
            elif evidence_type in {"figure", "table", "code", "data"}:
                if not nonempty_text(reference):
                    problems.append(f"empty {evidence_type} ref")
                else:
                    try:
                        evidence_path = safe_project_path(root, reference)
                        if not path_under_any(
                            root, evidence_path, ("work", "paper", "supporting")
                        ):
                            problems.append(f"file outside managed evidence paths: {reference}")
                        elif is_ephemeral_file(evidence_path):
                            problems.append(f"ephemeral file cannot be evidence: {reference}")
                        elif not evidence_path.is_file():
                            problems.append(f"missing file: {reference}")
                    except EngineError as exc:
                        problems.append(str(exc))
            elif evidence_type in {"literature", "official_rule"}:
                if not nonempty_text(reference):
                    problems.append(f"empty {evidence_type} ref")
            else:
                problems.append(f"unsupported evidence type: {evidence_type}")
        if problems:
            invalid[index] = problems
    duplicate_claim_ids = sorted(
        {value for value in claim_ids if claim_ids.count(value) > 1}
    )
    claim_ok = (
        isinstance(mapping, dict)
        and current_schema(mapping.get("schema_version"))
        and isinstance(ledger, dict)
        and current_schema(ledger.get("schema_version"))
        and bool(claims)
        and not invalid
        and not duplicate_claim_ids
    )
    add_finding(
        findings,
        "WRITE-002",
        "project_required",
        claim_ok,
        "关键结论已有 Claim–Evidence 映射" if claim_ok else "Claim–Evidence 映射为空或不完整",
        {
            "claim_count": len(claims),
            "invalid_rows": invalid,
            "duplicate_claim_ids": duplicate_claim_ids,
        },
        "使用结构化 evidence（type/ref），并确保结果 ID 可解析、文件存在、文献/规则引用非空。",
    )
    freeze_ok, details = verify_freeze(root)
    add_finding(
        findings,
        "WRITE-003",
        "project_required",
        freeze_ok,
        "写作期间冻结证据未漂移" if freeze_ok else "写作期间冻结证据发生漂移",
        details,
        "停止润色，按变更协议回退并重新冻结。",
    )


def unresolved_review_blockers(report: dict[str, Any]) -> list[Any]:
    unresolved: list[Any] = []
    values = report.get("findings", [])
    for finding in values if isinstance(values, list) else []:
        if not isinstance(finding, dict):
            unresolved.append(finding)
            continue
        if finding.get("severity") == "blocker" and finding.get("status") != "fixed":
            unresolved.append(finding.get("id", finding))
        if finding.get("severity") == "major" and finding.get("status") == "open":
            unresolved.append(finding.get("id", finding))
        if (
            finding.get("class") == "official_hard"
            and finding.get("status") not in {"fixed", "not_applicable"}
        ):
            unresolved.append(finding.get("id", finding))
    return unresolved


def review_finding_errors(finding: Any) -> list[str]:
    if not isinstance(finding, dict):
        return ["finding must be an object"]
    errors: list[str] = []
    for field in ("id", "claim", "impact", "remediation"):
        if not nonempty_text(finding.get(field)):
            errors.append(f"{field} must be non-empty text")
    if finding.get("class") not in {
        "official_hard",
        "project_required",
        "quality_advisory",
    }:
        errors.append("class is invalid")
    if finding.get("severity") not in {"blocker", "major", "minor", "note"}:
        errors.append("severity is invalid")
    if finding.get("status") not in {
        "open",
        "fixed",
        "accepted_risk",
        "not_applicable",
    }:
        errors.append("status is invalid")
    evidence = finding.get("evidence")
    if (
        not isinstance(evidence, list)
        or not evidence
        or not all(nonempty_text(item) for item in evidence)
    ):
        errors.append("evidence must be a non-empty text array")
    if finding.get("owner_stage") not in {
        "design",
        "solve",
        "verify",
        "write",
        "delivery",
    }:
        errors.append("owner_stage is invalid")
    return errors


def audit_review(root: Path, findings: list[dict[str, Any]]) -> None:
    expected = {
        "model": root / "state" / "reviews" / "model_review.json",
        "repro": root / "state" / "reviews" / "repro_review.json",
        "judge": root / "state" / "reviews" / "judge_review.json",
    }
    problems: dict[str, Any] = {}
    for role, path in expected.items():
        if not path.exists():
            problems[role] = "missing"
            continue
        raw_report = read_json_or(path, {})
        report = raw_report if isinstance(raw_report, dict) else {}
        unresolved = unresolved_review_blockers(report) if report else ["invalid"]
        scope = report.get("scope")
        scope_ok = nonempty_text(scope) or (
            isinstance(scope, list)
            and bool(scope)
            and all(nonempty_text(item) for item in scope)
        )
        evidence_examined = report.get("evidence_examined")
        report_findings = report.get("findings")
        finding_errors: dict[int, list[str]] = {}
        finding_ids: list[str] = []
        if isinstance(report_findings, list):
            for index, finding in enumerate(report_findings):
                errors = review_finding_errors(finding)
                if errors:
                    finding_errors[index] = errors
                if isinstance(finding, dict) and nonempty_text(finding.get("id")):
                    finding_ids.append(finding["id"])
        duplicate_ids = sorted(
            {value for value in finding_ids if finding_ids.count(value) > 1}
        )
        shape_ok = (
            current_schema(report.get("schema_version"))
            and report.get("reviewer_role") == role
            and report.get("independent_context") is True
            and scope_ok
            and isinstance(evidence_examined, list)
            and bool(evidence_examined)
            and all(nonempty_text(item) for item in evidence_examined)
            and isinstance(report_findings, list)
            and not finding_errors
            and not duplicate_ids
            and nonempty_text(report.get("conclusion"))
        )
        if report.get("status") != "completed" or unresolved or not shape_ok:
            problems[role] = {
                "status": report.get("status"),
                "unresolved": unresolved,
                "shape_ok": shape_ok,
                "finding_errors": finding_errors,
                "duplicate_finding_ids": duplicate_ids,
            }
    reviews_ok = not problems
    add_finding(
        findings,
        "REVIEW-001",
        "project_required",
        reviews_ok,
        "三席复核完成且无未关闭 blocker" if reviews_ok else "三席复核缺失或仍有 blocker",
        problems,
        "分别在独立上下文完成建模席、复现席和评阅席；登记范围、已查证据、结论并关闭阻断项。",
    )
    gate_ok = gate_is_approved(root, "review_close")
    add_finding(
        findings,
        "GATE-G3",
        "project_required",
        gate_ok,
        "G3 三席复核已由团队关闭" if gate_ok else "G3 三席复核尚未由团队关闭",
        gate_data(root).get("gates", {}).get("review_close"),
        "团队审阅三席报告和修复证据后批准 review_close。",
    )


def scan_identity_terms(root: Path, terms: list[str]) -> list[dict[str, str]]:
    normalized = [term.strip() for term in terms if isinstance(term, str) and term.strip()]
    if not normalized:
        return []
    matches: list[dict[str, str]] = []

    def folded(value: str) -> str:
        return unicodedata.normalize("NFKC", value).casefold()

    def scan_text(text: str, location: str, where: str) -> None:
        folded_text = folded(text)
        for term in normalized:
            if folded(term) in folded_text:
                matches.append({"term": term, "path": location, "where": where})

    def scan_zip_bytes(data: bytes, location: str, depth: int = 0) -> None:
        if depth > 2:
            return
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                if archive.comment:
                    scan_text(
                        archive.comment.decode("utf-8", errors="replace"),
                        location,
                        "archive-comment",
                    )
                infos = archive.infolist()
                if len(infos) > MAX_ARCHIVE_MEMBERS:
                    return
                scanned_bytes = 0
                for info in infos:
                    member = info.filename.replace("\\", "/")
                    if info.is_dir():
                        continue
                    scan_text(member, f"{location}!{member}", "archive-member-name")
                    if info.file_size > 5_000_000:
                        continue
                    scanned_bytes += info.file_size
                    if scanned_bytes > 50_000_000:
                        return
                    try:
                        payload = archive.read(info)
                    except (OSError, RuntimeError, zipfile.BadZipFile):
                        continue
                    suffix = Path(member).suffix.casefold()
                    if suffix in TEXT_SUFFIXES or suffix in {".xml", ".rels"}:
                        decoded = payload.decode("utf-8", errors="replace")
                        scan_text(decoded, f"{location}!{member}", "archive-text")
                        if suffix in {".xml", ".rels"}:
                            try:
                                parsed = ET.fromstring(payload)
                                xml_text = "".join(
                                    node.text or "" for node in parsed.iter()
                                )
                                scan_text(
                                    xml_text,
                                    f"{location}!{member}",
                                    "archive-xml-text",
                                )
                            except ET.ParseError:
                                pass
                    elif suffix in {".docx", ".xlsx", ".xlsm", ".pptx", ".zip"}:
                        scan_zip_bytes(payload, f"{location}!{member}", depth + 1)
        except (OSError, zipfile.BadZipFile):
            return

    for relative in ("paper", "supporting", "delivery"):
        for path in iter_evidence_files(root / relative):
            rel = relative_posix(root, path)
            for term in normalized:
                if folded(term) in folded(rel):
                    matches.append({"term": term, "path": rel, "where": "path"})
            suffix = path.suffix.casefold()
            if path.stat().st_size > 20_000_000:
                continue
            if suffix in TEXT_SUFFIXES:
                try:
                    scan_text(
                        path.read_text(encoding="utf-8-sig", errors="replace"),
                        rel,
                        "text",
                    )
                except OSError:
                    continue
            elif suffix in {".docx", ".xlsx", ".xlsm", ".pptx", ".zip"}:
                try:
                    scan_zip_bytes(path.read_bytes(), rel)
                except OSError:
                    continue
    return matches


def inspect_support_archive(
    root: Path, archive_path: Path, manifest_path: Path
) -> tuple[bool, dict[str, Any]]:
    def normalized_name(raw: str) -> str:
        value = unicodedata.normalize("NFKC", raw.replace("\\", "/"))
        while value.startswith("./"):
            value = value[2:]
        return value

    def unsafe_name(raw: str) -> bool:
        value = unicodedata.normalize("NFKC", raw.replace("\\", "/"))
        while value.startswith("./"):
            value = value[2:]
        parts = value.split("/")
        reserved = {"con", "prn", "aux", "nul"} | {
            f"{prefix}{number}"
            for prefix in ("com", "lpt")
            for number in range(1, 10)
        }
        return (
            not value
            or "\x00" in value
            or value.startswith("/")
            or bool(re.match(r"^[A-Za-z]:", value))
            or any(part in {"", ".", ".."} for part in parts)
            or any(part.endswith((" ", ".")) or ":" in part for part in parts)
            or any(part.split(".", 1)[0].casefold() in reserved for part in parts)
        )

    manifest = read_json_or(manifest_path, {})
    declared = manifest.get("files", []) if isinstance(manifest, dict) else []
    declared_map: dict[str, dict[str, Any]] = {}
    manifest_errors: list[str] = []
    if not isinstance(manifest, dict) or not current_schema(manifest.get("schema_version")):
        manifest_errors.append("schema_version 不受支持")
    if not isinstance(declared, list):
        manifest_errors.append("files 必须是列表")
    for index, item in enumerate(declared if isinstance(declared, list) else []):
        if (
            not isinstance(item, dict)
            or not nonempty_text(item.get("path"))
            or not nonempty_text(item.get("source_path"))
        ):
            manifest_errors.append(
                f"files[{index}] 必须是含 path/source_path/size/sha256 的 object"
            )
            continue
        raw_name = item["path"]
        name = normalized_name(raw_name)
        if unsafe_name(raw_name):
            manifest_errors.append(f"不安全清单路径: {raw_name}")
            continue
        if name.casefold() in {value.casefold() for value in declared_map}:
            manifest_errors.append(f"清单路径重复: {name}")
            continue
        if (
            not isinstance(item.get("size"), int)
            or isinstance(item.get("size"), bool)
            or item.get("size", -1) < 0
            or not re.fullmatch(
                r"[0-9a-fA-F]{64}", str(item.get("sha256", ""))
            )
        ):
            manifest_errors.append(f"清单缺少有效 size/sha256: {name}")
            continue
        if "purpose" in item and not nonempty_text(item.get("purpose")):
            manifest_errors.append(f"清单 purpose 必须是非空文本: {name}")
            continue
        declared_map[name] = item
    declared_paths = set(declared_map)
    source_mismatches: list[str] = []
    source_paths: list[str] = []
    for name, item in declared_map.items():
        try:
            source_path = safe_project_path(root, item["source_path"])
            if not path_under_any(
                root, source_path, ("work", "paper", "supporting")
            ):
                raise EngineError(
                    f"source_path 不在 work/paper/supporting 托管目录: {item['source_path']}"
                )
            if is_ephemeral_file(source_path):
                raise EngineError(
                    f"临时/系统文件不可作为归档源证据: {item['source_path']}"
                )
            source_relative = relative_posix(root, source_path)
            source_paths.append(source_relative)
        except EngineError as exc:
            source_mismatches.append(str(exc))
            continue
        if not source_path.is_file() or source_path.is_symlink():
            source_mismatches.append(
                f"归档成员 {name} 的项目源文件不存在或不是普通文件: {item.get('source_path')}"
            )
        elif (
            source_path.stat().st_size != item.get("size")
            or sha256_file(source_path).casefold() != str(item.get("sha256")).casefold()
        ):
            source_mismatches.append(f"归档成员 {name} 与项目源文件/清单哈希不符")
    if archive_path.suffix.casefold() != ".zip":
        return False, {
            "reason": "RAR 无法用标准库可靠解析",
            "declared_count": len(declared_paths),
            "manifest_errors": manifest_errors,
            "source_mismatches": source_mismatches,
            "source_paths": sorted(source_paths),
            "requires_manual_archive_check": True,
    }
    try:
        with zipfile.ZipFile(archive_path) as archive:
            all_infos = archive.infolist()
            infos = [item for item in all_infos if not item.is_dir()]
            special_members: list[str] = []
            for item in all_infos:
                if item.create_system != 3:
                    continue
                file_type = stat.S_IFMT((item.external_attr >> 16) & 0xFFFF)
                allowed_types = {0, stat.S_IFDIR} if item.is_dir() else {0, stat.S_IFREG}
                if file_type not in allowed_types:
                    special_members.append(item.filename)
            special_members.sort()
            total_uncompressed = sum(item.file_size for item in infos)
            if (
                len(all_infos) > MAX_ARCHIVE_MEMBERS
                or total_uncompressed > MAX_ARCHIVE_UNCOMPRESSED_BYTES
            ):
                return False, {
                    "reason": "ZIP 成员数或解压后总大小超过安全审计上限",
                    "safety_limit_exceeded": True,
                    "requires_manual_archive_check": True,
                    "declared_count": len(declared_paths),
                    "archive_count": len(infos),
                    "archive_entry_count": len(all_infos),
                    "total_uncompressed_bytes": total_uncompressed,
                    "manifest_errors": manifest_errors,
                    "source_mismatches": source_mismatches,
                    "source_paths": sorted(source_paths),
                    "special_members": special_members,
                }
            bad_member = archive.testzip()
            raw_names = [item.filename for item in infos]
            unsafe = sorted(
                [name for name in raw_names if unsafe_name(name)]
                + [
                    item.filename
                    for item in all_infos
                    if item.is_dir()
                    and unsafe_name(item.filename.rstrip("/\\"))
                ]
            )
            normalized = [normalized_name(name) for name in raw_names]
            counts: dict[str, int] = {}
            for name in normalized:
                key = name.casefold()
                counts[key] = counts.get(key, 0) + 1
            duplicates = sorted(
                {name for name in normalized if counts.get(name.casefold(), 0) > 1}
            )
            members = set(normalized)
            content_mismatches: list[str] = []
            for info, name in zip(infos, normalized):
                declared_item = declared_map.get(name)
                if not declared_item:
                    continue
                payload = archive.read(info)
                if (
                    len(payload) != declared_item.get("size")
                    or hashlib.sha256(payload).hexdigest().casefold()
                    != str(declared_item.get("sha256")).casefold()
                ):
                    content_mismatches.append(name)
    except (
        OSError,
        RuntimeError,
        NotImplementedError,
        zipfile.BadZipFile,
        zipfile.LargeZipFile,
    ) as exc:
        return False, {"reason": f"ZIP 无法读取: {exc}"}
    missing = sorted(declared_paths - members)
    undeclared = sorted(members - declared_paths)
    ok = (
        bool(declared_paths)
        and bad_member is None
        and not manifest_errors
        and not source_mismatches
        and not unsafe
        and not duplicates
        and not special_members
        and not missing
        and not undeclared
        and not content_mismatches
    )
    return ok, {
        "declared_count": len(declared_paths),
        "archive_count": len(members),
        "archive_entry_count": len(all_infos),
        "total_uncompressed_bytes": total_uncompressed,
        "manifest_errors": manifest_errors,
        "source_mismatches": source_mismatches,
        "source_paths": sorted(source_paths),
        "missing": missing,
        "undeclared": undeclared,
        "unsafe": unsafe,
        "duplicates": duplicates,
        "special_members": special_members,
        "content_mismatches": content_mismatches,
        "bad_member": bad_member,
    }


def submission_signature(path: Path) -> tuple[bool, str]:
    """Check only signatures that can be decided without document parsing."""
    suffix = path.suffix.casefold()
    try:
        header = path.read_bytes()[:8]
    except OSError as exc:
        return False, str(exc)
    if suffix == ".pdf":
        return header.startswith(b"%PDF-"), "PDF magic"
    if suffix == ".docx":
        try:
            with zipfile.ZipFile(path) as archive:
                names = set(archive.namelist())
            return "word/document.xml" in names, "DOCX package"
        except (OSError, zipfile.BadZipFile) as exc:
            return False, f"DOCX package error: {exc}"
    if suffix == ".doc":
        return header.startswith(bytes.fromhex("D0CF11E0A1B11AE1")), "OLE Word magic"
    return False, "unsupported extension"


def archive_signature(path: Path) -> tuple[bool, str]:
    try:
        header = path.read_bytes()[:8]
    except OSError as exc:
        return False, str(exc)
    suffix = path.suffix.casefold()
    if suffix == ".zip":
        return header.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")), "ZIP magic"
    if suffix == ".rar":
        return header.startswith(b"Rar!\x1a\x07"), "RAR magic"
    return False, "unsupported extension"


def audit_delivery(root: Path, findings: list[dict[str, Any]]) -> None:
    raw_attestation = read_json_or(root / "state" / "compliance_attestation.json", {})
    attestation = raw_attestation if isinstance(raw_attestation, dict) else {}
    checks = attestation.get("checks", {})
    checks = checks if isinstance(checks, dict) else {}
    run = read_json_or(root / "state" / "run_manifest.json", {})
    run = run if isinstance(run, dict) else {}
    problem = read_json_or(root / "state" / "problem_contract.json", {})
    problem = problem if isinstance(problem, dict) else {}
    _, data_inventory_errors, self_sourced_paths = validate_data_inventory(
        root, problem.get("data_inventory")
    )
    program_usage = run.get("program_usage")
    support_required = attestation.get("support_required")
    declaration = attestation.get("ai_declaration_mode")
    official_checks = (
        "paper_and_print_match",
        "abstract_page_checked",
        "body_page_limit_checked",
        "anonymous_checked",
        "citations_checked",
        "appendix_checked",
        "ai_declaration_checked",
        "ai_usage_truth_confirmed",
    )
    project_checks = (
        "official_rules_rechecked_on_submission_day",
        "final_render_checked",
    )
    required_attestation_keys = {
        "schema_version",
        "final_paper",
        "support_required",
        "no_support_reason",
        "support_archive",
        "support_manifest",
        "ai_declaration_mode",
        "ai_detail_pdf",
        "forbidden_identity_terms",
        "checks",
    }
    required_check_keys = set(official_checks) | set(project_checks) | {
        "support_replayed",
        "archive_contents_checked",
    }
    missing_official = [name for name in official_checks if checks.get(name) is not True]
    attestation_schema_errors: list[str] = []
    if not required_attestation_keys.issubset(attestation):
        attestation_schema_errors.append("missing top-level fields")
    if not required_check_keys.issubset(checks):
        attestation_schema_errors.append("missing check fields")
    if any(not isinstance(checks.get(name), bool) for name in required_check_keys):
        attestation_schema_errors.append("check fields must be boolean")
    if not isinstance(attestation.get("support_required"), bool):
        attestation_schema_errors.append("support_required must be boolean")
    if attestation.get("ai_declaration_mode") not in {"used", "none"}:
        attestation_schema_errors.append("ai_declaration_mode")
    if not all(
        isinstance(attestation.get(name), str)
        for name in (
            "final_paper",
            "no_support_reason",
            "support_archive",
            "support_manifest",
            "ai_detail_pdf",
        )
    ):
        attestation_schema_errors.append("path fields must be strings")
    attestation_schema_ok = (
        current_schema(attestation.get("schema_version"))
        and not attestation_schema_errors
    )
    add_finding(
        findings,
        "DELIVERY-001",
        "official_hard",
        attestation_schema_ok and not missing_official,
        "团队已完成官方事项人工确认"
        if attestation_schema_ok and not missing_official
        else "合规声明 schema 或官方事项人工确认未完成",
        {
            "schema_version": attestation.get("schema_version"),
            "schema_errors": attestation_schema_errors,
            "missing_checks": missing_official,
        },
        "由团队逐项确认纸电一致、页数/摘要、匿名、引用/附录与 AI 声明真实性。",
    )
    missing_project = [name for name in project_checks if checks.get(name) is not True]
    if support_required is True and checks.get("archive_contents_checked") is not True:
        missing_project.append("archive_contents_checked")
    if program_usage in {"code", "interactive"} and checks.get("support_replayed") is not True:
        missing_project.append("support_replayed")
    add_finding(
        findings,
        "DELIVERY-003",
        "project_required",
        not missing_project,
        "项目级交付复核完成" if not missing_project else "项目级交付复核未完成",
        missing_project,
        "重新核验当日规则和最终渲染；有支撑材料时查归档，有程序/交互工件时重放。",
    )

    paper_value = attestation.get("final_paper", "")
    paper_ok = False
    paper_status = "fail"
    paper_details: dict[str, Any] = {"path": paper_value}
    if nonempty_text(paper_value):
        try:
            paper_path = safe_project_path(root, paper_value)
            signature_ok, signature_kind = (
                submission_signature(paper_path) if paper_path.is_file() else (False, "missing")
            )
            delivery_papers = [
                item
                for item in iter_evidence_files(root / "delivery")
                if item.suffix.casefold() in {".pdf", ".docx", ".doc"}
            ]
            in_delivery = relative_posix(root, paper_path).startswith("delivery/")
            size = paper_path.stat().st_size if paper_path.is_file() else None
            structural_ok = (
                paper_path.is_file()
                and paper_path.suffix.casefold() in {".pdf", ".docx", ".doc"}
                and signature_ok
                and not is_ephemeral_file(paper_path)
                and in_delivery
                and len(delivery_papers) == 1
            )
            if structural_ok and size is not None and size <= MAX_SUBMISSION_BYTES:
                paper_ok = True
                paper_status = "pass"
            elif structural_ok and size is not None and size <= 20 * 1024 * 1024:
                paper_status = "review"
            paper_details.update(
                {
                    "exists": paper_path.is_file(),
                    "suffix": paper_path.suffix.casefold(),
                    "size": size,
                    "signature_ok": signature_ok,
                    "signature_kind": signature_kind,
                    "in_delivery": in_delivery,
                    "delivery_paper_count": len(delivery_papers),
                }
            )
        except EngineError as exc:
            paper_details["error"] = str(exc)
    add_finding(
        findings,
        "FORMAT-F01",
        "official_hard",
        paper_ok,
        "最终电子论文格式和大小通过确定性检查"
        if paper_ok
        else (
            "论文大小位于 20 MB 的十进制/二进制歧义区间，需压缩或人工核对提交系统"
            if paper_status == "review"
            else "最终电子论文缺失、文件数/签名/位置不符或明确超过 20 MB"
        ),
        paper_details,
        "delivery 中只保留一个最终 PDF/Word；确认文件签名并压缩到 20,000,000 字节以内。",
        status=paper_status,
    )

    support_value = attestation.get("support_archive", "")
    manifest_value = attestation.get("support_manifest", "")
    executable_artifact_present = bool(
        iter_evidence_files(root / "work" / "code")
    )
    delivery_archives = [
        item
        for item in iter_evidence_files(root / "delivery")
        if item.suffix.casefold() in {".zip", ".rar"}
    ]
    support_ok = (
        support_required is False
        and program_usage == "none"
        and not executable_artifact_present
        and declaration == "none"
        and not data_inventory_errors
        and not self_sourced_paths
        and nonempty_text(attestation.get("no_support_reason"))
        and len(attestation.get("no_support_reason", "").strip()) >= 12
        and support_value == ""
        and manifest_value == ""
        and not delivery_archives
    )
    support_status = "pass" if support_ok else "fail"
    support_details: dict[str, Any] = {
        "required": support_required,
        "program_usage": program_usage,
        "executable_artifact_present": executable_artifact_present,
        "ai_declaration_mode": declaration,
        "ai_used_requires_support": declaration == "used",
        "data_inventory_errors": data_inventory_errors,
        "self_sourced_used_paths": self_sourced_paths,
        "no_support_reason": attestation.get("no_support_reason"),
        "declared_archive": support_value,
        "delivery_archives": [relative_posix(root, path) for path in delivery_archives],
    }
    archive_path: Path | None = None
    manifest_path: Path | None = None
    if (
        support_required is True
        and attestation.get("no_support_reason") == ""
        and nonempty_text(support_value)
        and nonempty_text(manifest_value)
    ):
        try:
            archive_path = safe_project_path(root, support_value)
            manifest_path = safe_project_path(root, manifest_value)
            support_details.update(
                {
                    "archive": support_value,
                    "manifest": manifest_value,
                    "archive_exists": archive_path.is_file(),
                    "manifest_exists": manifest_path.is_file(),
                    "size": archive_path.stat().st_size if archive_path.is_file() else None,
                }
            )
            signature_ok, signature_kind = (
                archive_signature(archive_path)
                if archive_path.is_file()
                else (False, "missing")
            )
            structural_ok = (
                archive_path.is_file()
                and manifest_path.is_file()
                and archive_path.suffix.casefold() in {".zip", ".rar"}
                and signature_ok
                and not is_ephemeral_file(archive_path)
                and not is_ephemeral_file(manifest_path)
                and relative_posix(root, archive_path).startswith("delivery/")
                and relative_posix(root, manifest_path).startswith("supporting/")
                and len(delivery_archives) == 1
            )
            size = archive_path.stat().st_size if archive_path.is_file() else None
            if structural_ok and size is not None and size <= MAX_SUBMISSION_BYTES:
                support_ok = True
                support_status = "pass"
            elif structural_ok and size is not None and size <= 20 * 1024 * 1024:
                support_status = "review"
            support_details.update(
                {
                    "signature_ok": signature_ok,
                    "signature_kind": signature_kind,
                    "manifest_under_supporting": relative_posix(root, manifest_path).startswith(
                        "supporting/"
                    ),
                    "delivery_archive_count": len(delivery_archives),
                }
            )
        except EngineError as exc:
            support_details["error"] = str(exc)
    add_finding(
        findings,
        "FORMAT-F02",
        "official_hard",
        support_ok,
        "支撑材料存在且格式/大小可接受，或确无程序且已确认不需要"
        if support_ok
        else (
            "支撑材料大小位于 20 MB 的十进制/二进制歧义区间，需压缩或人工核对提交系统"
            if support_status == "review"
            else "支撑材料要求、文件数、签名、位置、格式或大小不合格"
        ),
        support_details,
        "明确 support_required；需要时指定一个不超过 20 MB 的 ZIP/RAR 和清单。",
        status=support_status,
    )

    archive_ok = False
    archive_details: dict[str, Any] = {}
    normalized_inputs, declared_input_errors = validate_declared_paths(
        root,
        run.get("declared_inputs"),
        "declared_inputs",
        RUNTIME_INPUT_BASES,
        require_files=True,
    )
    official_inputs, official_input_errors = validate_official_attachment_inputs(
        root, run.get("official_attachment_inputs"), normalized_inputs
    )
    declared_input_errors.extend(official_input_errors)
    official_input_paths = {item["path"] for item in official_inputs}
    if support_required is True and archive_path and manifest_path and support_ok:
        archive_ok, archive_details = inspect_support_archive(root, archive_path, manifest_path)
        required_runtime_sources = (
            {
                relative_posix(root, path)
                for path in iter_evidence_files(root / "work" / "code")
            }
            if program_usage in {"code", "interactive"}
            else set()
        )
        required_runtime_sources.update(
            set(normalized_inputs) - official_input_paths
        )
        required_runtime_sources.update(self_sourced_paths)
        declared_source_paths = set(archive_details.get("source_paths", []))
        missing_runtime_sources = sorted(
            required_runtime_sources - declared_source_paths
        )
        archive_details["declared_input_errors"] = declared_input_errors
        archive_details["data_inventory_errors"] = data_inventory_errors
        archive_details["official_attachment_exemptions"] = official_inputs
        archive_details["missing_runtime_sources"] = missing_runtime_sources
        if missing_runtime_sources or declared_input_errors or data_inventory_errors:
            archive_ok = False
        manual_archive_kind = (
            archive_path.suffix.casefold() == ".rar"
            or archive_details.get("safety_limit_exceeded") is True
        )
        if manual_archive_kind and checks.get("archive_contents_checked") is True:
            archive_ok = bool(archive_details.get("declared_count")) and not (
                archive_details.get("manifest_errors")
                or archive_details.get("source_mismatches")
                or archive_details.get("missing_runtime_sources")
                or archive_details.get("declared_input_errors")
                or archive_details.get("data_inventory_errors")
            )
            archive_details["manual_attestation_used"] = True
        add_finding(
            findings,
            "SUPPORT-001",
            "project_required",
            archive_ok,
            "归档内容与支撑材料清单一致" if archive_ok else "归档内容无法确认或与清单不一致",
            archive_details,
            "修复 ZIP/清单差异；RAR 或超过内置安全解压上限的 ZIP 必须完成人工内容确认并保留证据。",
        )

    replay_reports, rejected_replay_reports = replay_report_evidence(
        root, require_current_freeze=True
    )
    if program_usage == "code":
        replay_ok = bool(replay_reports) and checks.get("support_replayed") is True
        replay_status = "pass" if replay_ok else "fail"
    elif program_usage == "interactive":
        replay_reports, rejected_replay_reports = manual_replay_report_evidence(
            root, require_current_freeze=True
        )
        replay_ok = bool(replay_reports) and checks.get("support_replayed") is True
        replay_status = "pass" if replay_ok else "fail"
    elif program_usage == "none":
        replay_ok = True
        replay_status = "not_applicable"
    else:
        replay_ok = False
        replay_status = "fail"
    add_finding(
        findings,
        "REPLAY-001",
        "project_required",
        replay_ok,
        "求解重放证据有效"
        if replay_status == "pass"
        else ("未使用程序，自动重放不适用" if replay_status == "not_applicable" else "缺少有效重放证据"),
        {
            "program_usage": program_usage,
            "passing_reports": replay_reports,
            "rejected_reports": rejected_replay_reports,
            "manual_procedure": run.get("manual_replay_procedure"),
        },
        "代码模式运行 replay 并保留 PASS 报告；交互模式记录实际人工重放步骤；无程序模式标记不适用。",
        status=replay_status,
    )

    change_log_path = root / "state" / "change_log.jsonl"
    change_chain_ok, change_errors, change_events = verify_event_chain(change_log_path)
    invalid_change_events: dict[int, list[str]] = {}
    for index, event in enumerate(change_events):
        event_errors: list[str] = []
        from_gate = event.get("from_gate")
        if event.get("event_type") != "reopen":
            event_errors.append("event_type")
        if from_gate not in GATES:
            event_errors.append("from_gate")
        elif event.get("cleared_gates") != list(GATES[GATES.index(from_gate) :]):
            event_errors.append("cleared_gates")
        if not nonempty_text(event.get("reason")):
            event_errors.append("reason")
        if event.get("recorded_by") != "engine":
            event_errors.append("recorded_by")
        if event_errors:
            invalid_change_events[index] = event_errors
    change_log_ok = (
        change_log_path.is_file()
        and change_chain_ok
        and not invalid_change_events
    )
    add_finding(
        findings,
        "CHANGE-001",
        "project_required",
        change_log_ok,
        "回退/重开日志链有效" if change_log_ok else "回退/重开日志缺失或哈希链损坏",
        {
            "events": len(change_events),
            "errors": change_errors,
            "invalid_events": invalid_change_events,
        },
        "保留 state/change_log.jsonl，并只通过 reopen 命令追加事件。",
    )

    ai_log_path = root / "state" / "ai_usage_log.jsonl"
    chain_ok, chain_errors, ai_events = verify_event_chain(ai_log_path)
    chain_ok = ai_log_path.is_file() and chain_ok
    required_ai_fields = (
        "tool",
        "model_or_version",
        "stage",
        "purpose",
        "prompt_approach_summary",
        "output_summary",
        "adoption_and_modification",
        "manual_verification",
    )
    superseded: set[str] = set()
    supersede_errors_by_event: dict[str, str] = {}
    seen_ai_ids: set[str] = set()
    for event in ai_events:
        supersedes = event.get("supersedes")
        if supersedes is not None:
            if not nonempty_text(supersedes) or supersedes not in seen_ai_ids:
                event_id = str(event.get("event_id", "unknown"))
                supersede_errors_by_event[event_id] = (
                    f"{event_id} supersedes 未知或非前序事件 {supersedes}"
                )
            else:
                superseded.add(supersedes)
        if nonempty_text(event.get("event_id")):
            seen_ai_ids.add(event["event_id"])
    active_ai_events = [
        event for event in ai_events if event.get("event_id") not in superseded
    ]
    supersede_errors = [
        message
        for event_id, message in supersede_errors_by_event.items()
        if event_id not in superseded
    ]
    invalid_ai_events = [
        item.get("event_id", index)
        for index, item in enumerate(active_ai_events)
        if item.get("event_type") != "ai_usage"
        or item.get("stage") not in STAGES
        or not all(nonempty_text(item.get(field)) for field in required_ai_fields)
        or str(item.get("model_or_version", "")).casefold() == "unspecified"
    ]
    ai_consistent = (
        chain_ok
        and declaration in {"used", "none"}
        and not invalid_ai_events
        and not supersede_errors
    )
    if active_ai_events:
        ai_consistent = ai_consistent and declaration == "used"
    elif declaration == "used":
        ai_consistent = False
    add_finding(
        findings,
        "AI-001",
        "project_required",
        ai_consistent,
        "AI 日志链与声明模式一致" if ai_consistent else "AI 日志损坏或与声明模式矛盾",
        {
            "log_exists": ai_log_path.is_file(),
            "events": len(ai_events),
            "active_events": len(active_ai_events),
            "superseded_events": sorted(superseded),
            "supersede_errors": supersede_errors,
            "declaration": declaration,
            "errors": chain_errors,
            "invalid_events": invalid_ai_events,
        },
        "只根据真实使用记录选择 used/none；不得补造交互或隐瞒使用。",
    )
    if declaration == "used":
        detail_value = attestation.get("ai_detail_pdf", "")
        detail_ok = False
        detail_evidence: dict[str, Any] = {
            "path": detail_value,
            "support_required": support_required,
            "support_archive_structural_ok": support_ok,
            "support_archive_contents_ok": archive_ok,
        }
        if nonempty_text(detail_value):
            try:
                detail_path = safe_project_path(root, detail_value)
                detail_relative = relative_posix(root, detail_path) if detail_path.exists() else ""
                matching_manifest_members: list[str] = []
                if nonempty_text(manifest_value):
                    try:
                        detail_manifest = read_json_or(
                            safe_project_path(root, manifest_value), {}
                        )
                        declared = detail_manifest.get("files", [])
                        matching_manifest_members = [
                            str(item.get("path")).replace("\\", "/").lstrip("./")
                            for item in declared
                            if isinstance(item, dict)
                            and Path(str(item.get("path", "")).replace("\\", "/")).name
                            == OFFICIAL_AI_DETAIL_NAME
                            and str(item.get("source_path", "")).replace("\\", "/").lstrip("./")
                            == detail_relative
                        ]
                    except EngineError:
                        matching_manifest_members = []
                pdf_signature_ok = (
                    submission_signature(detail_path)[0]
                    if detail_path.is_file()
                    else False
                )
                detail_ok = (
                    support_required is True
                    and support_ok
                    and archive_ok
                    and detail_path.is_file()
                    and detail_path.name == OFFICIAL_AI_DETAIL_NAME
                    and detail_path.suffix.casefold() == ".pdf"
                    and pdf_signature_ok
                    and detail_relative.startswith("supporting/")
                    and bool(matching_manifest_members)
                )
                detail_evidence.update(
                    {
                        "support_required": support_required,
                        "support_archive_structural_ok": support_ok,
                        "support_archive_contents_ok": archive_ok,
                        "exists": detail_path.is_file(),
                        "name": detail_path.name,
                        "pdf_signature_ok": pdf_signature_ok,
                        "under_supporting": detail_relative.startswith("supporting/"),
                        "archive_members_with_official_basename": matching_manifest_members,
                    }
                )
            except EngineError as exc:
                detail_evidence["error"] = str(exc)
        add_finding(
            findings,
            "AI-002",
            "official_hard",
            detail_ok,
            "AI 使用详情 PDF 已随支撑归档提交且文件名/格式正确"
            if detail_ok
            else "AI 使用详情 PDF 未实际进入可核验的支撑归档，或文件名/格式不正确",
            detail_evidence,
            f"在支撑材料中提供 {OFFICIAL_AI_DETAIL_NAME}，内容须与真实日志一致。",
        )

    terms = attestation.get("forbidden_identity_terms", [])
    matches = scan_identity_terms(root, terms if isinstance(terms, list) else [])
    identity_ok = not matches and checks.get("anonymous_checked") is True
    add_finding(
        findings,
        "ANON-001",
        "official_hard",
        identity_ok,
        "已知身份词扫描无命中且人工匿名检查完成" if identity_ok else "身份词扫描命中或人工匿名检查未完成",
        {"terms_count": len(terms) if isinstance(terms, list) else 0, "matches": matches},
        "录入队员姓名、学校全称/简称和赛区等精确词，扫描后再人工检查图片、元数据和未知简称。",
    )
    terms_ok = (
        isinstance(terms, list)
        and bool(terms)
        and all(nonempty_text(term) for term in terms)
    )
    add_finding(
        findings,
        "ANON-002",
        "project_required",
        terms_ok,
        "身份词取证清单已登记" if terms_ok else "身份词取证清单为空或格式不合法",
        {"terms_count": len(terms) if isinstance(terms, list) else 0},
        "登记队员姓名、学校全称/简称和赛区等精确词，作为自动扫描的已知词表。",
    )

    freeze_ok, freeze_details = verify_freeze(root)
    add_finding(
        findings,
        "DELIVERY-002",
        "project_required",
        freeze_ok,
        "交付时冻结证据无漂移" if freeze_ok else "交付时冻结证据已漂移",
        freeze_details,
        "按变更协议回退、重算、重审并重新冻结。",
    )
    gate_ok = gate_is_approved(root, "submission_lock")
    add_finding(
        findings,
        "GATE-G4",
        "project_required",
        gate_ok,
        "G4 最终提交已由团队批准" if gate_ok else "G4 最终提交尚未由团队批准",
        gate_data(root).get("gates", {}).get("submission_lock"),
        "三名队员核对最终文件和真实披露后批准 submission_lock。",
    )


AUDITORS = {
    "intake": audit_intake,
    "design": audit_design,
    "solve": audit_solve,
    "verify": audit_verify,
    "write": audit_write,
    "review": audit_review,
    "delivery": audit_delivery,
}


def audit_project(root: Path, stage: str, write_report: bool = True) -> dict[str, Any]:
    if stage not in STAGES:
        raise EngineError(f"未知阶段: {stage}")
    findings: list[dict[str, Any]] = []
    for current in STAGES[: STAGES.index(stage) + 1]:
        try:
            AUDITORS[current](root, findings)
        except Exception as exc:
            add_finding(
                findings,
                f"ENGINE-{current.upper()}",
                "project_required",
                False,
                f"审计阶段无法完成: {type(exc).__name__}: {exc}",
                {"exception_type": type(exc).__name__},
                "修复缺失/损坏的账本后重试。",
            )
    blockers = [
        item
        for item in findings
        if item.get("status") not in {"pass", "not_applicable"}
        and item.get("severity") == "blocker"
    ]
    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now(),
        "stage": stage,
        "scope": list(STAGES[: STAGES.index(stage) + 1]),
        "outcome": "PASS" if not blockers else "FAIL",
        "summary": {
            "checks": len(findings),
            "passed": sum(
                item.get("status") in {"pass", "not_applicable"}
                for item in findings
            ),
            "blockers": len(blockers),
        },
        "claim": "PASS 表示未发现本引擎当前可判定的阻断项，不等于官方机构认证。",
        "findings": findings,
    }
    if write_report and not (root / "reports" / "final_lock.json").exists():
        write_json(root / "reports" / f"audit_{stage}.json", report)
    return report


def gate_prerequisite_blockers(root: Path, gate: str) -> list[str]:
    stage = GATE_STAGE[gate]
    findings: list[dict[str, Any]] = []
    for current in STAGES[: STAGES.index(stage) + 1]:
        try:
            AUDITORS[current](root, findings)
        except Exception as exc:
            return [f"ENGINE-{current.upper()}:{type(exc).__name__}"]
    ignored = {
        "problem_selection": {"GATE-G0"},
        "model_contract": {"GATE-G1"},
        "result_freeze": {"GATE-G2"},
        "review_close": {"GATE-G3"},
        "submission_lock": {"GATE-G4"},
    }[gate]
    if gate == "result_freeze" and not (root / "state" / "frozen_manifest.json").exists():
        ignored.add("FREEZE-001")
    return [
        item["id"]
        for item in findings
        if item.get("id") not in ignored
        and item.get("status") not in {"pass", "not_applicable"}
        and item.get("severity") == "blocker"
    ]


def reserved_approver(value: str) -> bool:
    normalized = unicodedata.normalize("NFKC", value).strip().casefold()
    tokens = set(re.findall(r"[a-z0-9]+", normalized))
    reserved_tokens = {
        "ai",
        "agent",
        "assistant",
        "system",
        "openai",
        "copilot",
        "deepseek",
        "qwen",
    }
    obvious_model_token = any(
        token in reserved_tokens
        or token.startswith("chatgpt")
        or token.startswith("codex")
        or bool(re.fullmatch(r"gpt\d*", token))
        for token in tokens
    )
    obvious_chinese_marker = any(
        marker in normalized for marker in ("机器人", "人工智能", "智能体")
    ) or normalized in {"模型", "助手", "系统", "模拟", "文心一言", "通义千问", "豆包"}
    return (
        not normalized
        or obvious_model_token
        or obvious_chinese_marker
    )


def approve_gate(root: Path, gate: str, approved_by: str, note: str) -> dict[str, Any]:
    ensure_unlocked(root)
    if gate not in GATES:
        raise EngineError(f"未知门禁: {gate}")
    if not nonempty_text(approved_by) or not nonempty_text(note):
        raise EngineError("批准人和批准说明均不能为空")
    raw_config = read_json(root / "cumcm-project.json")
    config = raw_config if isinstance(raw_config, dict) else {}
    data = gate_data(root)
    gates = data.setdefault("gates", {})
    index = GATES.index(gate)
    upstream = [item for item in GATES[:index] if not gate_is_approved(root, item)]
    if upstream:
        raise EngineError(f"上游门禁尚未批准: {', '.join(upstream)}")
    blockers = gate_prerequisite_blockers(root, gate)
    if blockers:
        raise EngineError(f"门禁前置审计未通过: {', '.join(blockers)}")
    kind = "simulation" if config.get("mode") == "training" else "team_attested"
    if kind == "team_attested":
        if reserved_approver(approved_by):
            raise EngineError("competition 模式拒绝把 AI/Agent 名称记录为团队批准人")
        if len(note.strip()) < 8:
            raise EngineError("competition 模式的批准说明过短，无法追溯真实复核")
    evidence_sha256, evidence_files = gate_evidence_digest(root, gate)
    gates[gate] = {
        "approved": True,
        "approved_by": approved_by,
        "approved_at": utc_now(),
        "approval_kind": kind,
        "note": note,
        "evidence_sha256": evidence_sha256,
        "evidence_files": evidence_files,
    }
    write_json(root / "state" / "human_gates.json", data)
    return gates[gate]


def archive_existing(root: Path, path: Path, label: str) -> str | None:
    if not path.exists():
        return None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    history = root / "reports" / "history" / f"{stamp}-{uuid.uuid4().hex[:8]}"
    history.mkdir(parents=True, exist_ok=False)
    destination = history / f"{label}-{path.name}"
    shutil.move(str(path), str(destination))
    return relative_posix(root, destination)


def invalidate_from_gate(root: Path, from_gate: str, reason: str) -> dict[str, Any]:
    data = gate_data(root)
    gates = data.setdefault("gates", {})
    start = GATES.index(from_gate)
    cleared: list[str] = []
    for gate in GATES[start:]:
        previous = gates.get(gate, {})
        if previous.get("approved"):
            cleared.append(gate)
        gates[gate] = {
            "approved": False,
            "approved_by": None,
            "approved_at": None,
            "approval_kind": None,
            "note": f"invalidated: {reason}",
            "evidence_sha256": None,
            "evidence_files": [],
        }
    write_json(root / "state" / "human_gates.json", data)
    archived: list[str] = []
    if start <= GATES.index("result_freeze"):
        value = archive_existing(
            root, root / "state" / "frozen_manifest.json", "invalidated"
        )
        if value:
            archived.append(value)
        for replay_path in sorted((root / "reports").glob("replay_*.json")):
            value = archive_existing(root, replay_path, "invalidated")
            if value:
                archived.append(value)
        for replay_path in sorted((root / "reports").glob("manual_replay_*.json")):
            value = archive_existing(root, replay_path, "invalidated")
            if value:
                archived.append(value)
    value = archive_existing(root, root / "reports" / "final_lock.json", "invalidated")
    if value:
        archived.append(value)
    return {"cleared": cleared, "archived": archived}


def reopen_project(root: Path, from_gate: str, reason: str) -> dict[str, Any]:
    if from_gate not in GATES:
        raise EngineError(f"未知门禁: {from_gate}")
    if len(reason.strip()) < 8:
        raise EngineError("回退原因过短，无法审计")
    change_log_path = root / "state" / "change_log.jsonl"
    chain_ok, chain_errors, _ = verify_event_chain(change_log_path)
    if not chain_ok:
        raise EngineError(
            "回退日志已有损坏，拒绝改变门禁或归档状态: " + "; ".join(chain_errors)
        )
    start = GATES.index(from_gate)
    invalidation = invalidate_from_gate(root, from_gate, reason)
    event = append_chained_event(
        change_log_path,
        {
            "event_type": "reopen",
            "from_gate": from_gate,
            "reason": reason,
            "cleared_gates": list(GATES[start:]),
            "recorded_by": "engine",
        },
    )
    return {
        "cleared": invalidation["cleared"],
        "archived": invalidation["archived"],
        "event_id": event["event_id"],
    }


def freeze_project(root: Path) -> dict[str, Any]:
    ensure_unlocked(root)
    if not gate_is_approved(root, "result_freeze"):
        raise EngineError("冻结前必须由团队批准 result_freeze 门禁")
    blockers = gate_prerequisite_blockers(root, "result_freeze")
    if blockers:
        raise EngineError(f"冻结前审计未通过: {', '.join(blockers)}")
    manifest_path = root / "state" / "frozen_manifest.json"
    if manifest_path.exists():
        ok, details = verify_freeze(root)
        if ok:
            return read_json(manifest_path)
        raise EngineError(f"已有冻结清单且发生漂移；先 reopen。详情: {details}")
    files = frozen_scope(root)
    if not files:
        raise EngineError("冻结范围为空")
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "created_at": utc_now(),
        "algorithm": "sha256",
        "files": build_hash_manifest(root, files),
    }
    manifest["manifest_sha256"] = hashlib.sha256(canonical_json(manifest)).hexdigest()
    write_json(manifest_path, manifest)
    return manifest


def verify_lock(root: Path) -> tuple[bool, dict[str, Any]]:
    lock_path = root / "reports" / "final_lock.json"
    if not lock_path.exists():
        return False, {"error": "missing final_lock.json"}
    raw_lock = read_json(lock_path)
    lock = raw_lock if isinstance(raw_lock, dict) else {}
    expected_items = lock.get("files", [])
    if not isinstance(expected_items, list):
        expected_items = []
    expected = {
        item.get("path"): item
        for item in expected_items
        if isinstance(item, dict) and nonempty_text(item.get("path"))
    }
    expected_keys = {
        "schema_version",
        "locked_at",
        "algorithm",
        "audit_outcome",
        "scope",
        "files",
        "lock_sha256",
    }
    expected_scope = [
        "cumcm-project.json",
        "state/**",
        "work/**",
        "paper/**",
        "supporting/**",
        "delivery/**",
        "reports/audit_*.json",
        "reports/replay_*.json",
        "reports/manual_replay_*.json",
    ]
    locked_at_valid = False
    if isinstance(lock, dict) and nonempty_text(lock.get("locked_at")):
        try:
            locked_at_valid = (
                datetime.fromisoformat(lock["locked_at"].replace("Z", "+00:00")).tzinfo
                is not None
            )
        except (TypeError, ValueError):
            locked_at_valid = False
    malformed_manifest = not (
        isinstance(lock, dict)
        and set(lock) == expected_keys
        and valid_hash_manifest_rows(expected_items)
        and len(expected) == len(expected_items)
        and lock.get("algorithm") == "sha256"
        and lock.get("audit_outcome") == "PASS"
        and lock.get("scope") == expected_scope
        and locked_at_valid
    )
    stored_lock_hash = lock.get("lock_sha256")
    lock_body = dict(lock)
    lock_body.pop("lock_sha256", None)
    computed_lock_hash = hashlib.sha256(canonical_json(lock_body)).hexdigest()
    lock_hash_valid = stored_lock_hash == computed_lock_hash
    schema_valid = (
        current_schema(lock.get("schema_version"))
    )
    missing: list[str] = []
    changed: list[str] = []
    for relative, item in expected.items():
        try:
            path = safe_project_path(root, relative)
        except EngineError:
            missing.append(relative)
            continue
        if not path.is_file():
            missing.append(relative)
        elif sha256_file(path) != item.get("sha256") or path.stat().st_size != item.get("size"):
            changed.append(relative)
    current_scope = {
        relative_posix(root, path): path for path in final_lock_scope(root)
    }
    added = sorted(set(current_scope) - set(expected))
    freeze_ok, freeze_details = verify_freeze(root)
    ok = (
        bool(expected)
        and schema_valid
        and not malformed_manifest
        and lock_hash_valid
        and not missing
        and not changed
        and not added
        and freeze_ok
    )
    return ok, {
        "missing": missing,
        "changed": changed,
        "added": added,
        "manifest_well_formed": not malformed_manifest,
        "schema_valid": schema_valid,
        "lock_hash_valid": lock_hash_valid,
        "freeze_valid": freeze_ok,
        "freeze_details": freeze_details,
    }


def lock_project(root: Path) -> dict[str, Any]:
    existing = root / "reports" / "final_lock.json"
    if existing.exists():
        ok, details = verify_lock(root)
        if not ok:
            raise EngineError(f"最终锁定已漂移；必须 reopen: {details}")
        return read_json(existing)
    report = audit_project(root, "delivery", write_report=True)
    if report["outcome"] != "PASS":
        blocker_ids = [
            item["id"]
            for item in report["findings"]
            if item.get("severity") == "blocker" and item.get("status") != "pass"
        ]
        raise EngineError(f"交付审计未通过: {', '.join(blocker_ids)}")
    files = final_lock_scope(root)
    if not files:
        raise EngineError("最终锁定范围为空")
    lock = {
        "schema_version": SCHEMA_VERSION,
        "locked_at": utc_now(),
        "algorithm": "sha256",
        "audit_outcome": report["outcome"],
        "scope": [
            "cumcm-project.json",
            "state/**",
            "work/**",
            "paper/**",
            "supporting/**",
            "delivery/**",
            "reports/audit_*.json",
            "reports/replay_*.json",
            "reports/manual_replay_*.json",
        ],
        "files": build_hash_manifest(root, files),
    }
    lock["lock_sha256"] = hashlib.sha256(canonical_json(lock)).hexdigest()
    write_json(existing, lock)
    return lock


def replay_project(root: Path, timeout_seconds: int) -> dict[str, Any]:
    """Rebuild outputs from only declared project files in a clean workspace."""
    ensure_unlocked(root)
    if timeout_seconds < 1 or timeout_seconds > 7200:
        raise EngineError("replay timeout 必须在 1–7200 秒之间")
    raw_run = read_json(root / "state" / "run_manifest.json")
    run = raw_run if isinstance(raw_run, dict) else {}
    if not current_schema(run.get("schema_version")):
        raise EngineError("run_manifest.schema_version 不受支持")
    if run.get("program_usage") != "code":
        raise EngineError("自动 replay 仅适用于 program_usage=code；交互/无程序模式使用相应人工或不适用证据")
    command = run.get("command")
    declared_inputs, input_errors = validate_declared_paths(
        root,
        run.get("declared_inputs"),
        "declared_inputs",
        RUNTIME_INPUT_BASES,
        require_files=True,
    )
    official_inputs, official_input_errors = validate_official_attachment_inputs(
        root, run.get("official_attachment_inputs"), declared_inputs
    )
    declared_outputs, output_errors = validate_declared_paths(
        root,
        run.get("expected_outputs"),
        "expected_outputs",
        RUNTIME_OUTPUT_BASES,
        require_files=True,
    )
    if not declared_outputs:
        output_errors.append("代码重放必须声明非空 expected_outputs")
    current_output_names = {
        relative_posix(root, path)
        for base in RUNTIME_OUTPUT_BASES
        for path in iter_evidence_files(root / base)
    }
    undeclared_current_outputs = sorted(
        current_output_names - set(declared_outputs)
    )
    if undeclared_current_outputs:
        output_errors.append(
            "项目含未声明结果/图表，拒绝重放: "
            + ", ".join(undeclared_current_outputs)
        )
    if set(declared_inputs) & set(declared_outputs):
        input_errors.append("declared_inputs 与 expected_outputs 不得重叠")
    argv, command_errors = command_contract_errors(
        root, run, declared_inputs, declared_outputs
    )
    contract_errors = (
        input_errors + official_input_errors + output_errors + command_errors
    )
    if contract_errors:
        raise EngineError("运行清单不满足洁净重放契约: " + "; ".join(contract_errors))
    declared_executable = argv[0]
    argv = resolved_replay_argv(argv)
    runtime_paths = list(iter_evidence_files(root / "work" / "code"))
    runtime_paths.extend(safe_project_path(root, value) for value in declared_inputs)
    runtime_map = {relative_posix(root, path): path for path in runtime_paths}
    entry_relative = relative_posix(root, safe_project_path(root, run["entrypoint"]))
    if entry_relative not in runtime_map:
        raise EngineError("entrypoint 未进入洁净运行副本")
    initial_runtime_evidence = build_hash_manifest(root, runtime_map.values())
    initial_runtime_manifest = {
        item["path"]: item for item in initial_runtime_evidence
    }
    project_output_manifest = {
        item["path"]: item
        for item in build_hash_manifest(
            root, (safe_project_path(root, value) for value in declared_outputs)
        )
    }

    started_at = utc_now()
    timed_out = False
    execution_error = ""
    returncode: int | None = None
    stdout = ""
    stderr = ""
    solve_blockers: list[str] = []
    freeze_exists = (root / "state" / "frozen_manifest.json").exists()
    run_manifest_sha256 = sha256_file(root / "state" / "run_manifest.json")
    frozen_manifest_sha256 = (
        sha256_file(root / "state" / "frozen_manifest.json")
        if freeze_exists
        else None
    )
    freeze_ok = not freeze_exists
    freeze_details: dict[str, Any] = (
        {"note": "尚未冻结，仅验证运行与新生成输出"}
        if not freeze_exists
        else {}
    )
    frozen_output_manifest: dict[str, dict[str, Any]] = {}
    if freeze_exists:
        original_freeze_ok, original_freeze_details = verify_freeze(root)
        if not original_freeze_ok:
            raise EngineError(f"冻结证据已漂移，拒绝重放: {original_freeze_details}")
        raw_freeze = read_json(root / "state" / "frozen_manifest.json")
        frozen_output_manifest = {
            item["path"]: item
            for item in raw_freeze.get("files", [])
            if isinstance(item, dict) and nonempty_text(item.get("path"))
        }
        freeze_details = {"original_freeze": original_freeze_details}
    output_evidence: list[dict[str, Any]] = []
    fresh_outputs = False
    unexpected_outputs: list[str] = []
    project_output_mismatches: list[str] = []
    unexpected_workspace_files: list[str] = []
    runtime_input_drift: list[str] = []
    with tempfile.TemporaryDirectory(prefix="cumcm-replay-") as temporary:
        sandbox = Path(temporary) / "project"
        sandbox.mkdir(parents=True)
        for relative in (*RUNTIME_INPUT_BASES, *RUNTIME_OUTPUT_BASES):
            (sandbox / relative).mkdir(parents=True, exist_ok=True)
        try:
            for relative, source in runtime_map.items():
                destination = safe_project_path(sandbox, relative)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
        except OSError as exc:
            raise EngineError(f"无法建立洁净运行副本: {exc}") from exc
        try:
            replay_environment = os.environ.copy()
            replay_environment["PYTHONDONTWRITEBYTECODE"] = "1"
            replay_environment["CUMCM_REPLAY_CLEAN_WORKSPACE"] = "1"
            replay_environment["TMP"] = str(Path(temporary) / "tmp")
            replay_environment["TEMP"] = str(Path(temporary) / "tmp")
            Path(replay_environment["TEMP"]).mkdir(parents=True, exist_ok=True)
            completed = subprocess.run(
                argv,
                cwd=sandbox,
                env=replay_environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_seconds,
                check=False,
            )
            returncode = completed.returncode
            stdout = completed.stdout[-20_000:]
            stderr = completed.stderr[-20_000:]
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            stdout = (exc.stdout or "")[-20_000:] if isinstance(exc.stdout, str) else ""
            stderr = (exc.stderr or "")[-20_000:] if isinstance(exc.stderr, str) else ""
        except OSError as exc:
            execution_error = f"{type(exc).__name__}: {exc}"

        generated_files: dict[str, Path] = {}
        for base in RUNTIME_OUTPUT_BASES:
            for path in iter_evidence_files(sandbox / base):
                generated_files[relative_posix(sandbox, path)] = path
        unexpected_outputs = sorted(set(generated_files) - set(declared_outputs))
        for relative in declared_outputs:
            output_path = safe_project_path(sandbox, relative)
            item: dict[str, Any] = {
                "path": relative,
                "freshly_created": output_path.is_file() and not output_path.is_symlink(),
            }
            if item["freshly_created"]:
                item["size"] = output_path.stat().st_size
                item["sha256"] = sha256_file(output_path)
            output_evidence.append(item)
        fresh_outputs = all(item["freshly_created"] for item in output_evidence)
        project_output_mismatches = sorted(
            item["path"]
            for item in output_evidence
            if not item.get("freshly_created")
            or item["path"] not in project_output_manifest
            or item.get("size") != project_output_manifest[item["path"]].get("size")
            or item.get("sha256")
            != project_output_manifest[item["path"]].get("sha256")
        )

        current_runtime_paths: list[Path] = []
        for base in RUNTIME_INPUT_BASES:
            current_runtime_paths.extend(iter_evidence_files(sandbox / base))
        current_runtime_manifest = {
            item["path"]: item
            for item in build_hash_manifest(sandbox, current_runtime_paths)
        }
        runtime_input_drift = sorted(
            path
            for path in set(initial_runtime_manifest) | set(current_runtime_manifest)
            if initial_runtime_manifest.get(path) != current_runtime_manifest.get(path)
        )
        allowed_workspace_files = set(current_runtime_manifest) | set(generated_files)
        unexpected_workspace_files = sorted(
            relative_posix(sandbox, path)
            for path in iter_evidence_files(sandbox)
            if relative_posix(sandbox, path) not in allowed_workspace_files
        )

        if freeze_exists:
            regenerated_mismatches: list[str] = []
            for item in output_evidence:
                frozen_item = frozen_output_manifest.get(item["path"])
                if (
                    not item.get("freshly_created")
                    or not frozen_item
                    or item.get("size") != frozen_item.get("size")
                    or item.get("sha256") != frozen_item.get("sha256")
                ):
                    regenerated_mismatches.append(item["path"])
            freeze_ok = not regenerated_mismatches
            freeze_details["regenerated_output_mismatches"] = regenerated_mismatches

        for relative in (
            "cumcm-project.json",
            "state/problem_contract.json",
            "state/run_manifest.json",
            "state/result_ledger.json",
        ):
            source = root / relative
            if source.is_file():
                destination = sandbox / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
        solve_findings: list[dict[str, Any]] = []
        audit_solve(sandbox, solve_findings, require_replay=False)
        solve_blockers = [
            item["id"]
            for item in solve_findings
            if item.get("status") not in {"pass", "not_applicable"}
            and item.get("severity") == "blocker"
        ]
    outcome = (
        "PASS"
        if returncode == 0
        and not timed_out
        and not execution_error
        and fresh_outputs
        and not project_output_mismatches
        and not unexpected_outputs
        and not unexpected_workspace_files
        and not runtime_input_drift
        and not solve_blockers
        and freeze_ok
        else "FAIL"
    )
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_path = root / "reports" / f"replay_{stamp}_{uuid.uuid4().hex[:8]}.json"
    report = {
        "schema_version": SCHEMA_VERSION,
        "started_at": started_at,
        "finished_at": utc_now(),
        "declared_entrypoint": run.get("entrypoint"),
        "declared_command": command,
        "declared_executable": declared_executable,
        "resolved_command": argv,
        "isolated_workspace": True,
        "clean_workspace": True,
        "runtime_files": sorted(runtime_map),
        "runtime_evidence": initial_runtime_evidence,
        "declared_inputs": declared_inputs,
        "official_attachment_inputs": official_inputs,
        "timeout_seconds": timeout_seconds,
        "timed_out": timed_out,
        "execution_error": execution_error,
        "returncode": returncode,
        "stdout_tail": stdout,
        "stderr_tail": stderr,
        "expected_outputs": output_evidence,
        "project_output_mismatches": project_output_mismatches,
        "unexpected_outputs": unexpected_outputs,
        "unexpected_workspace_files": unexpected_workspace_files,
        "runtime_input_drift": runtime_input_drift,
        "solve_blockers": solve_blockers,
        "run_manifest_sha256": run_manifest_sha256,
        "frozen_manifest_sha256": frozen_manifest_sha256,
        "freeze_checked": freeze_exists,
        "freeze_valid": freeze_ok,
        "freeze_details": freeze_details,
        "engine_sha256": sha256_file(Path(__file__).resolve()),
        "outcome": outcome,
        "report_path": relative_posix(root, report_path),
    }
    report["report_sha256"] = hashlib.sha256(canonical_json(report)).hexdigest()
    write_json(report_path, report)
    return report


def project_status(root: Path) -> dict[str, Any]:
    stage_status: dict[str, str] = {}
    first_blocked: str | None = None
    for stage in STAGES:
        report = audit_project(root, stage, write_report=False)
        stage_status[stage] = report["outcome"]
        if first_blocked is None and report["outcome"] != "PASS":
            first_blocked = stage
    freeze_ok, freeze_details = verify_freeze(root)
    lock_exists = (root / "reports" / "final_lock.json").exists()
    lock_ok, lock_details = verify_lock(root) if lock_exists else (False, {"error": "not locked"})
    data = gate_data(root)
    effective_gates: dict[str, dict[str, Any]] = {}
    for gate in GATES:
        raw_item = data.get("gates", {}).get(gate, {})
        item = dict(raw_item) if isinstance(raw_item, dict) else {}
        item["recorded_approved"] = item.get("approved") is True
        item["approved"] = gate_is_approved(root, gate)
        item["effective_approved"] = item["approved"]
        effective_gates[gate] = item
    return {
        "project": str(root),
        "stages": stage_status,
        "next_stage": first_blocked,
        "gates": effective_gates,
        "freeze": {"valid": freeze_ok, **freeze_details},
        "lock": {"exists": lock_exists, "valid": lock_ok, **lock_details},
    }


def command_record_decision(args: argparse.Namespace) -> dict[str, Any]:
    root = project_root(args.root)
    ensure_unlocked(root)
    if not all(
        nonempty_text(getattr(args, field))
        for field in (
            "question",
            "choice",
            "alternatives",
            "evidence",
            "impact",
            "approved_by",
        )
    ):
        raise EngineError("决策的问题、选择、备选、证据和决定者均不能为空")
    if args.question not in question_ids(root):
        raise EngineError(f"决策引用未知问题 ID: {args.question}")
    config = read_json_or(root / "cumcm-project.json", {})
    if (
        isinstance(config, dict)
        and config.get("mode") == "competition"
        and reserved_approver(args.approved_by)
    ):
        raise EngineError("competition 模式的建模决策必须由参赛队确认，不能把 AI/Agent 写成决定者")
    affected_gate = AFFECTS_GATE[args.affects]
    event = append_chained_event(
        root / "state" / "decision_ledger.jsonl",
        {
            "event_type": "decision",
            "question_id": args.question,
            "choice": args.choice,
            "alternatives": args.alternatives,
            "evidence": args.evidence,
            "impact": args.impact,
            "decided_by": args.approved_by,
            "affects_stage": args.affects,
            "invalidates_from": affected_gate,
        },
    )
    invalidation = None
    effective_gate = affected_gate
    if effective_gate is None and (root / "state" / "frozen_manifest.json").exists():
        effective_gate = "result_freeze"
    if effective_gate is not None:
        invalidation = invalidate_from_gate(
            root,
            effective_gate,
            f"decision {event['event_id']} affects {args.affects}",
        )
    return {"event": event, "invalidation": invalidation}


def command_record_ai(args: argparse.Namespace) -> dict[str, Any]:
    root = project_root(args.root)
    ensure_unlocked(root)
    if not all(
        nonempty_text(getattr(args, field))
        for field in (
            "tool",
            "model",
            "stage",
            "purpose",
            "prompt_summary",
            "output_summary",
            "adoption",
            "verification",
        )
    ):
        raise EngineError("AI 使用事件的工具、模型、阶段、用途、输入/输出摘要、采用方式和验证均不能为空")
    if args.model.strip().casefold() == "unspecified":
        raise EngineError("--model 必须填写实际模型或版本，不能使用 unspecified")
    if args.supersedes is not None:
        records, errors = read_jsonl(root / "state" / "ai_usage_log.jsonl")
        if errors:
            raise EngineError(f"AI 日志已有损坏，拒绝追加修正: {'; '.join(errors)}")
        prior_ids = {item.get("event_id") for item in records}
        if not nonempty_text(args.supersedes) or args.supersedes not in prior_ids:
            raise EngineError("--supersedes 必须指向 AI 日志中已存在的前序 event_id")
    event = append_chained_event(
        root / "state" / "ai_usage_log.jsonl",
        {
            "event_type": "ai_usage",
            "tool": args.tool,
            "model_or_version": args.model,
            "stage": args.stage,
            "purpose": args.purpose,
            "prompt_approach_summary": args.prompt_summary,
            "output_summary": args.output_summary,
            "adoption_and_modification": args.adoption,
            "manual_verification": args.verification,
            "supersedes": args.supersedes,
        },
    )
    invalidation = invalidate_from_gate(
        root,
        "submission_lock",
        f"AI usage event {event['event_id']} changes disclosure evidence",
    )
    return {"event": event, "invalidation": invalidation}


def command_record_manual_replay(args: argparse.Namespace) -> dict[str, Any]:
    root = project_root(args.root)
    ensure_unlocked(root)
    run_path = root / "state" / "run_manifest.json"
    run = read_json_or(run_path, {})
    if not isinstance(run, dict) or run.get("program_usage") != "interactive":
        raise EngineError("record-manual-replay 仅适用于 program_usage=interactive")
    if not nonempty_text(args.performed_by):
        raise EngineError("人工重放执行人不能为空")
    config = read_json_or(root / "cumcm-project.json", {})
    if (
        isinstance(config, dict)
        and config.get("mode") == "competition"
        and reserved_approver(args.performed_by)
    ):
        raise EngineError("competition 模式的人工重放必须由真实参赛队员确认")
    if not nonempty_text(args.workspace) or len(args.workspace.strip()) < 12:
        raise EngineError("--workspace 必须具体说明独立副本或干净目录，至少 12 个字符")
    if not nonempty_text(args.notes) or len(args.notes.strip()) < 12:
        raise EngineError("--notes 必须记录实际重放观察，至少 12 个字符")
    if not (
        args.confirm_clean_workspace
        and args.confirm_inputs_unchanged
        and args.confirm_outputs_regenerated
    ):
        raise EngineError("必须显式确认干净副本、输入未变和输出已重新生成")
    findings: list[dict[str, Any]] = []
    audit_solve(root, findings, require_replay=False)
    blockers = [
        item["id"]
        for item in findings
        if item["id"] in {"SOLVE-001", "SOLVE-002", "SOLVE-003"}
        and item.get("status") not in {"pass", "not_applicable"}
    ]
    if blockers:
        raise EngineError("人工重放记录前运行合同未通过: " + ", ".join(blockers))
    declared_inputs, input_errors = validate_declared_paths(
        root,
        run.get("declared_inputs"),
        "declared_inputs",
        RUNTIME_INPUT_BASES,
        require_files=True,
    )
    official_inputs, official_errors = validate_official_attachment_inputs(
        root, run.get("official_attachment_inputs"), declared_inputs
    )
    declared_outputs, output_errors = validate_declared_paths(
        root,
        run.get("expected_outputs"),
        "expected_outputs",
        RUNTIME_OUTPUT_BASES,
        require_files=True,
    )
    errors = input_errors + official_errors + output_errors
    if errors:
        raise EngineError("人工重放证据路径不合法: " + "; ".join(errors))
    runtime_paths = list(iter_evidence_files(root / "work" / "code"))
    runtime_paths.extend(safe_project_path(root, value) for value in declared_inputs)
    runtime_map = {relative_posix(root, path): path for path in runtime_paths}
    freeze_path = root / "state" / "frozen_manifest.json"
    freeze_exists = freeze_path.is_file()
    freeze_valid = verify_freeze(root)[0] if freeze_exists else False
    if freeze_exists and not freeze_valid:
        raise EngineError("当前冻结清单已漂移，不能记录后冻结人工重放")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_path = root / "reports" / f"manual_replay_{stamp}_{uuid.uuid4().hex[:8]}.json"
    report = {
        "schema_version": SCHEMA_VERSION,
        "recorded_at": utc_now(),
        "performed_by": args.performed_by.strip(),
        "workspace_description": args.workspace.strip(),
        "notes": args.notes.strip(),
        "procedure": run.get("manual_replay_procedure"),
        "declared_entrypoint": run.get("entrypoint"),
        "environment": run.get("environment"),
        "isolated_workspace": True,
        "inputs_unchanged": True,
        "outputs_regenerated": True,
        "runtime_files": sorted(runtime_map),
        "runtime_evidence": build_hash_manifest(root, runtime_map.values()),
        "declared_inputs": declared_inputs,
        "official_attachment_inputs": official_inputs,
        "expected_outputs": build_hash_manifest(
            root, [safe_project_path(root, value) for value in declared_outputs]
        ),
        "run_manifest_sha256": sha256_file(run_path),
        "frozen_manifest_sha256": sha256_file(freeze_path) if freeze_exists else "",
        "freeze_checked": freeze_exists,
        "freeze_valid": freeze_valid,
        "engine_sha256": sha256_file(Path(__file__).resolve()),
        "outcome": "PASS",
        "report_path": relative_posix(root, report_path),
    }
    report["report_sha256"] = hashlib.sha256(canonical_json(report)).hexdigest()
    write_json(report_path, report)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="CUMCM project state, freeze, and audit engine"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="initialize a non-destructive project skeleton")
    init.add_argument("root")
    init.add_argument("--year", type=int, required=True)
    init.add_argument("--mode", choices=("competition", "training"), default="competition")

    status = sub.add_parser("status", help="show cumulative stage/gate status")
    status.add_argument("root")

    audit = sub.add_parser("audit", help="run cumulative audit through a stage")
    audit.add_argument("root")
    audit.add_argument("--stage", choices=STAGES, required=True)

    decision = sub.add_parser("record-decision", help="append a hash-chained decision")
    decision.add_argument("root")
    decision.add_argument("--question", required=True)
    decision.add_argument("--choice", required=True)
    decision.add_argument("--alternatives", required=True)
    decision.add_argument("--evidence", required=True)
    decision.add_argument("--impact", required=True)
    decision.add_argument("--affects", choices=tuple(AFFECTS_GATE), required=True)
    decision.add_argument("--by", dest="approved_by", required=True)

    ai = sub.add_parser("record-ai", help="append a real AI-use event")
    ai.add_argument("root")
    ai.add_argument("--tool", required=True)
    ai.add_argument("--model", required=True)
    ai.add_argument("--stage", choices=STAGES, required=True)
    ai.add_argument("--purpose", required=True)
    ai.add_argument("--prompt-summary", required=True)
    ai.add_argument("--output-summary", required=True)
    ai.add_argument("--adoption", required=True)
    ai.add_argument("--verification", required=True)
    ai.add_argument("--supersedes")

    manual = sub.add_parser(
        "record-manual-replay",
        help="record a team-attested clean replay for an interactive artifact",
    )
    manual.add_argument("root")
    manual.add_argument("--by", dest="performed_by", required=True)
    manual.add_argument("--workspace", required=True)
    manual.add_argument("--notes", required=True)
    manual.add_argument("--confirm-clean-workspace", action="store_true")
    manual.add_argument("--confirm-inputs-unchanged", action="store_true")
    manual.add_argument("--confirm-outputs-regenerated", action="store_true")

    approve = sub.add_parser("approve", help="record a real or simulated human gate")
    approve.add_argument("root")
    approve.add_argument("--gate", choices=GATES, required=True)
    approve.add_argument("--by", dest="approved_by", required=True)
    approve.add_argument("--note", required=True)

    reopen = sub.add_parser("reopen", help="clear a gate and all downstream gates")
    reopen.add_argument("root")
    reopen.add_argument("--from", dest="from_gate", choices=GATES, required=True)
    reopen.add_argument("--reason", required=True)

    freeze = sub.add_parser("freeze", help="freeze upstream evidence with SHA-256")
    freeze.add_argument("root")

    replay = sub.add_parser(
        "replay", help="rebuild outputs from declared files in a clean project copy"
    )
    replay.add_argument("root")
    replay.add_argument("--timeout", type=int, default=600)

    lock = sub.add_parser("lock", help="lock a delivery that passes all audits")
    lock.add_argument("root")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            result: Any = {"initialized": str(initialize(args.root, args.year, args.mode))}
        elif args.command == "status":
            result = project_status(project_root(args.root))
        elif args.command == "audit":
            result = audit_project(project_root(args.root), args.stage)
        elif args.command == "record-decision":
            result = command_record_decision(args)
        elif args.command == "record-ai":
            result = command_record_ai(args)
        elif args.command == "record-manual-replay":
            result = command_record_manual_replay(args)
        elif args.command == "approve":
            result = approve_gate(
                project_root(args.root), args.gate, args.approved_by, args.note
            )
        elif args.command == "reopen":
            result = reopen_project(project_root(args.root), args.from_gate, args.reason)
        elif args.command == "freeze":
            result = freeze_project(project_root(args.root))
        elif args.command == "replay":
            result = replay_project(project_root(args.root), args.timeout)
        elif args.command == "lock":
            result = lock_project(project_root(args.root))
        else:  # pragma: no cover
            parser.error("unknown command")
            return 2
    except EngineError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.command in {"audit", "replay"} and result.get("outcome") != "PASS":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

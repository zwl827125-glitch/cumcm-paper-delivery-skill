from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "cumcm_engine.py"
SPEC = importlib.util.spec_from_file_location("cumcm_engine", MODULE_PATH)
assert SPEC and SPEC.loader
ENGINE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ENGINE)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def rewrite_single_event(path: Path, updates: dict[str, object]) -> None:
    event = json.loads(path.read_text(encoding="utf-8").strip())
    event.update(updates)
    body = dict(event)
    body.pop("event_hash", None)
    event["event_hash"] = ENGINE.hashlib.sha256(
        ENGINE.canonical_json(body)
    ).hexdigest()
    path.write_text(
        json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


class CumcmEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "project"
        ENGINE.initialize(str(self.root), 2026, "training")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def verify_rules(self) -> None:
        path = self.root / "state" / "rules_manifest.json"
        rules = ENGINE.read_json(path)
        rules["verified_at"] = "2026-09-10T00:00:00+00:00"
        rules["verified_by"] = "team"
        rules["confirmed_for_year"] = 2026
        for source in rules["sources"]:
            source["status"] = "verified"
        write_json(path, rules)

    def prepare_intake(self) -> None:
        self.verify_rules()
        write_json(
            self.root / "state" / "problem_contract.json",
            {
                "schema_version": 1,
                "problem_code": "A",
                "problem_title": "测试题",
                "problem_group": "本科组",
                "questions": [
                    {
                        "id": "Q1",
                        "task": "估计目标量",
                        "output": "估计值与区间",
                        "inputs": ["sample.csv"],
                        "depends_on": [],
                    }
                ],
                "data_inventory": [],
                "unknowns": [],
                "assumptions_to_test": [],
                "risk_register": [
                    {
                        "risk": "样本代表性不足",
                        "trigger": "分层结果显著漂移",
                        "fallback": "分层报告并降低结论强度",
                    }
                ],
            },
        )

    def prepare_design(self) -> None:
        self.prepare_intake()
        ENGINE.approve_gate(
            self.root, "problem_selection", "team", "simulation problem selection"
        )
        write_json(
            self.root / "state" / "model_contract.json",
            {
                "schema_version": 1,
                "questions": {
                    "Q1": {
                        "baseline": "样本均值",
                        "main_model": "稳健位置估计",
                        "fallback": "中位数",
                        "assumptions": ["样本代表目标总体"],
                        "validation": ["bootstrap 区间", "人工复算小样本"],
                    }
                },
                "global_dependencies": [],
            },
        )
        ENGINE.append_chained_event(
            self.root / "state" / "decision_ledger.jsonl",
            {
                "event_type": "decision",
                "question_id": "Q1",
                "choice": "稳健位置估计",
                "alternatives": "样本均值、中位数",
                "evidence": "异常值诊断",
                "impact": "改变点估计和区间",
                "decided_by": "team",
                "affects_stage": "design",
                "invalidates_from": "model_contract",
            },
        )
        ENGINE.approve_gate(
            self.root, "model_contract", "team", "simulation model review"
        )

    @staticmethod
    def solver_source() -> str:
        return (
            "import json\n"
            "from pathlib import Path\n"
            "path = Path('work/results/results.json')\n"
            "path.parent.mkdir(parents=True, exist_ok=True)\n"
            "path.write_text(json.dumps({'estimate': 1.25}, ensure_ascii=False, indent=2) + '\\n', encoding='utf-8')\n"
        )

    def prepare_solve_and_freeze(self) -> None:
        self.prepare_design()
        source = self.solver_source()
        (self.root / "work" / "code" / "main.py").write_text(source, encoding="utf-8")
        write_json(self.root / "work" / "results" / "results.json", {"estimate": 1.25})
        write_json(
            self.root / "state" / "run_manifest.json",
            {
                "schema_version": 1,
                "program_usage": "code",
                "entrypoint": "work/code/main.py",
                "command": "python work/code/main.py",
                "environment": {"python": "3.x", "dependencies": "standard-library"},
                "randomness": {"mode": "not_applicable", "seeds": []},
                "declared_inputs": [],
                "official_attachment_inputs": [],
                "expected_outputs": ["work/results/results.json"],
                "manual_replay_procedure": "",
                "no_program_reason": "",
            },
        )
        write_json(
            self.root / "state" / "result_ledger.json",
            {
                "schema_version": 1,
                "results": [
                    {
                        "id": "R-Q1-EST",
                        "question_id": "Q1",
                        "name": "目标量估计",
                        "value": 1.25,
                        "unit": "无量纲",
                        "precision": 0.01,
                        "data_scope": "全部测试样本",
                        "parameter_set": "default-v1",
                        "random_seed": "not_applicable",
                        "source_file": "work/results/results.json",
                        "generation_command": "python work/code/main.py",
                        "verification_status": "verified",
                    }
                ],
            },
        )
        checks = [
            {"type": "dimension_or_unit", "status": "pass", "evidence": "单位表"},
            {"type": "boundary_or_invariant", "status": "pass", "evidence": "范围检查"},
            {"type": "independent_evidence", "status": "pass", "evidence": "人工复算"},
            {
                "type": "uncertainty_or_robustness",
                "status": "pass",
                "evidence": "bootstrap",
            },
        ]
        write_json(
            self.root / "state" / "verification_report.json",
            {"schema_version": 1, "questions": {"Q1": {"checks": checks}}},
        )
        replay = ENGINE.replay_project(self.root, 30)
        self.assertEqual(replay["outcome"], "PASS", replay)
        ENGINE.approve_gate(
            self.root, "result_freeze", "team", "simulation result check"
        )
        ENGINE.freeze_project(self.root)

    def build_complete_project(self) -> None:
        self.prepare_solve_and_freeze()
        (self.root / "paper" / "paper.md").write_text(
            "# 测试论文\n\n估计值为 1.25。\n", encoding="utf-8"
        )
        write_json(
            self.root / "state" / "claim_evidence.json",
            {
                "schema_version": 1,
                "claims": [
                    {
                        "id": "C1",
                        "claim": "目标量估计为 1.25",
                        "evidence": [{"type": "result", "ref": "R-Q1-EST"}],
                    }
                ],
            },
        )
        for role in ("model", "repro", "judge"):
            write_json(
                self.root / "state" / "reviews" / f"{role}_review.json",
                {
                    "schema_version": 1,
                    "reviewer_role": role,
                    "independent_context": True,
                    "scope": ["Q1", "paper", "delivery"],
                    "evidence_examined": [
                        "state/model_contract.json",
                        "state/result_ledger.json",
                        "paper/paper.md",
                    ],
                    "status": "completed",
                    "findings": [],
                    "conclusion": "证据链完整，未发现未关闭阻断项。",
                },
            )
        ENGINE.approve_gate(
            self.root, "review_close", "team", "simulation reviews closed"
        )

        support_source = self.root / "supporting" / "main.py"
        support_source.write_text(self.solver_source(), encoding="utf-8")
        write_json(
            self.root / "supporting" / "file_manifest.json",
            {
                "schema_version": 1,
                "files": [
                    {
                        "path": "main.py",
                        "source_path": "work/code/main.py",
                        "purpose": "求解",
                        "size": support_source.stat().st_size,
                        "sha256": ENGINE.sha256_file(support_source),
                    }
                ],
            },
        )
        archive = self.root / "delivery" / "支撑材料.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as handle:
            handle.write(support_source, "main.py")
        (self.root / "delivery" / "论文.pdf").write_bytes(b"%PDF-1.4\n%test\n")

        replay = ENGINE.replay_project(self.root, 30)
        self.assertEqual(replay["outcome"], "PASS", replay)
        compliance = ENGINE.read_json(
            self.root / "state" / "compliance_attestation.json"
        )
        compliance.update(
            {
                "final_paper": "delivery/论文.pdf",
                "support_required": True,
                "support_archive": "delivery/支撑材料.zip",
                "support_manifest": "supporting/file_manifest.json",
                "ai_declaration_mode": "none",
                "forbidden_identity_terms": ["示例大学", "张三"],
            }
        )
        for key in compliance["checks"]:
            compliance["checks"][key] = True
        write_json(self.root / "state" / "compliance_attestation.json", compliance)
        ENGINE.approve_gate(
            self.root, "submission_lock", "team", "simulation final submission check"
        )

    def make_replay_project(self, command: str, source: str, stale_output: bool) -> None:
        self.prepare_intake()
        (self.root / "work" / "code" / "main.py").write_text(source, encoding="utf-8")
        (self.root / "work" / "results" / "out.json").write_text(
            '{"value": 1}\n', encoding="utf-8"
        )
        write_json(
            self.root / "state" / "run_manifest.json",
            {
                "schema_version": 1,
                "program_usage": "code",
                "entrypoint": "work/code/main.py",
                "command": command,
                "environment": {"python": "3.x"},
                "randomness": {"mode": "not_applicable", "seeds": []},
                "declared_inputs": [],
                "official_attachment_inputs": [],
                "expected_outputs": ["work/results/out.json"],
                "manual_replay_procedure": "",
                "no_program_reason": "",
            },
        )
        write_json(
            self.root / "state" / "result_ledger.json",
            {
                "schema_version": 1,
                "results": [
                    {
                        "id": "R1",
                        "question_id": "Q1",
                        "name": "值",
                        "value": 1,
                        "unit": "无量纲",
                        "precision": 1,
                        "data_scope": "测试数据",
                        "parameter_set": "default",
                        "random_seed": "not_applicable",
                        "source_file": "work/results/out.json",
                        "verification_status": "candidate",
                    }
                ],
            },
        )

    def test_init_refuses_to_overwrite(self) -> None:
        with self.assertRaises(ENGINE.EngineError):
            ENGINE.initialize(str(self.root), 2026, "training")

    def test_init_refuses_existing_managed_paths_without_config(self) -> None:
        legacy = Path(self.temporary.name) / "legacy"
        source = legacy / "work" / "code" / "important.py"
        source.parent.mkdir(parents=True)
        source.write_text("valuable user work\n", encoding="utf-8")
        with self.assertRaisesRegex(ENGINE.EngineError, "拒绝初始化覆盖"):
            ENGINE.initialize(str(legacy), 2026, "training")
        self.assertEqual(source.read_text(encoding="utf-8"), "valuable user work\n")
        self.assertFalse((legacy / "cumcm-project.json").exists())

    def test_hash_chain_detects_manual_edit(self) -> None:
        path = self.root / "state" / "decision_ledger.jsonl"
        ENGINE.append_chained_event(
            path,
            {
                "question_id": "Q1",
                "choice": "A",
                "alternatives": "B",
                "evidence": "test",
                "impact": "none",
                "decided_by": "team",
            },
        )
        ok, errors, _ = ENGINE.verify_event_chain(path)
        self.assertTrue(ok, errors)
        path.write_text(
            path.read_text(encoding="utf-8").replace('"choice": "A"', '"choice": "X"'),
            encoding="utf-8",
        )
        ok, errors, _ = ENGINE.verify_event_chain(path)
        self.assertFalse(ok)
        self.assertTrue(any("event_hash" in item for item in errors))

    def test_gate_requires_readiness_and_rejects_agent_identity(self) -> None:
        with self.assertRaisesRegex(ENGINE.EngineError, "RULES-001"):
            ENGINE.approve_gate(self.root, "problem_selection", "team", "not ready yet")
        self.prepare_intake()
        config = ENGINE.read_json(self.root / "cumcm-project.json")
        config["mode"] = "competition"
        write_json(self.root / "cumcm-project.json", config)
        for obvious_ai in (
            "Codex",
            "OpenAI Agent",
            "GPT-5",
            "Claude AI",
            "AI 审阅员",
            "通义千问",
        ):
            with self.subTest(obvious_ai=obvious_ai):
                with self.assertRaisesRegex(ENGINE.EngineError, "AI/Agent"):
                    ENGINE.approve_gate(
                        self.root,
                        "problem_selection",
                        obvious_ai,
                        "attempted non-human approval",
                    )
        for ambiguous_human_name in ("Claude", "Kimi", "Ernie", "Magenta"):
            with self.subTest(ambiguous_human_name=ambiguous_human_name):
                self.assertFalse(ENGINE.reserved_approver(ambiguous_human_name))
        approval = ENGINE.approve_gate(
            self.root,
            "problem_selection",
            "队员A",
            "三名参赛队员已共同核对题意与选题风险",
        )
        self.assertEqual(approval["approval_kind"], "team_attested")

    def test_complete_project_passes_and_lock_covers_all_evidence(self) -> None:
        self.build_complete_project()
        report = ENGINE.audit_project(self.root, "delivery", write_report=True)
        self.assertEqual(report["outcome"], "PASS", report)
        lock = ENGINE.lock_project(self.root)
        locked_paths = {item["path"] for item in lock["files"]}
        self.assertIn("state/model_contract.json", locked_paths)
        self.assertIn("state/decision_ledger.jsonl", locked_paths)
        self.assertIn("state/claim_evidence.json", locked_paths)
        self.assertIn("state/reviews/model_review.json", locked_paths)
        ok, details = ENGINE.verify_lock(self.root)
        self.assertTrue(ok, details)

        model_path = self.root / "state" / "model_contract.json"
        model_path.write_text(model_path.read_text(encoding="utf-8") + " ", encoding="utf-8")
        (self.root / "state" / "unexpected.txt").write_text("drift", encoding="utf-8")
        ok, details = ENGINE.verify_lock(self.root)
        self.assertFalse(ok)
        self.assertIn("state/model_contract.json", details["changed"])
        self.assertIn("state/unexpected.txt", details["added"])

    def test_decision_change_invalidates_downstream_gates_and_freeze(self) -> None:
        self.build_complete_project()
        result = ENGINE.command_record_decision(
            SimpleNamespace(
                root=str(self.root),
                question="Q1",
                choice="替代模型",
                alternatives="原稳健模型",
                evidence="新边界测试暴露偏差",
                impact="重算全部结果",
                affects="design",
                approved_by="team",
            )
        )
        self.assertIsNotNone(result["invalidation"])
        gates = ENGINE.gate_data(self.root)["gates"]
        self.assertTrue(gates["problem_selection"]["approved"])
        for gate in ENGINE.GATES[1:]:
            self.assertFalse(gates[gate]["approved"])
        self.assertFalse((self.root / "state" / "frozen_manifest.json").exists())

    def test_direct_evidence_edit_invalidates_bound_gate(self) -> None:
        self.build_complete_project()
        self.assertTrue(ENGINE.gate_is_approved(self.root, "review_close"))
        self.assertTrue(ENGINE.gate_is_approved(self.root, "submission_lock"))
        paper = self.root / "paper" / "paper.md"
        paper.write_text(paper.read_text(encoding="utf-8") + "\n改写结论。\n", encoding="utf-8")
        self.assertFalse(ENGINE.gate_is_approved(self.root, "review_close"))
        self.assertFalse(ENGINE.gate_is_approved(self.root, "submission_lock"))

    def test_ephemeral_python_cache_does_not_invalidate_freeze(self) -> None:
        self.prepare_solve_and_freeze()
        cache = self.root / "work" / "code" / "__pycache__" / "helper.pyc"
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(b"temporary bytecode")
        freeze_ok, details = ENGINE.verify_freeze(self.root)
        self.assertTrue(freeze_ok, details)
        self.assertTrue(ENGINE.gate_is_approved(self.root, "result_freeze"))

    def test_drifted_existing_freeze_requires_reopen_before_reapproval(self) -> None:
        self.prepare_solve_and_freeze()
        write_json(self.root / "work" / "results" / "results.json", {"estimate": 9.9})
        with self.assertRaisesRegex(ENGINE.EngineError, "FREEZE-001"):
            ENGINE.approve_gate(
                self.root, "result_freeze", "team", "simulation reapproval attempt"
            )

    def test_replay_rebuilds_output_in_isolated_copy(self) -> None:
        source = (
            "from pathlib import Path\n"
            "Path('work/results').mkdir(parents=True, exist_ok=True)\n"
            "Path('work/results/out.json').write_text('{\\\"value\\\": 1}\\n', encoding='utf-8')\n"
        )
        self.make_replay_project(
            "python work/code/main.py --threshold=0.5", source, stale_output=False
        )
        report = ENGINE.replay_project(self.root, 30)
        self.assertEqual(report["outcome"], "PASS", report)
        self.assertTrue(report["isolated_workspace"])
        self.assertTrue(report["clean_workspace"])
        self.assertEqual(
            (self.root / "work" / "results" / "out.json").read_text(encoding="utf-8"),
            '{"value": 1}\n',
        )

    def test_replay_rejects_stale_output_from_noop(self) -> None:
        self.make_replay_project("python work/code/main.py", "pass\n", stale_output=True)
        report = ENGINE.replay_project(self.root, 30)
        self.assertEqual(report["outcome"], "FAIL")
        self.assertFalse(report["expected_outputs"][0]["freshly_created"])

    def test_replay_does_not_replace_explicit_missing_venv(self) -> None:
        self.make_replay_project(
            r"C:\definitely-missing-cumcm-venv\python.exe work/code/main.py",
            "pass\n",
            stale_output=True,
        )
        report = ENGINE.replay_project(self.root, 30)
        self.assertEqual(report["outcome"], "FAIL")
        self.assertEqual(
            report["declared_executable"],
            r"C:\definitely-missing-cumcm-venv\python.exe",
        )
        self.assertTrue(report["execution_error"])

    def test_replay_rejects_external_script_even_with_internal_entrypoint(self) -> None:
        outside = Path(self.temporary.name) / "outside_solver.py"
        outside.write_text(self.solver_source(), encoding="utf-8")
        self.make_replay_project(
            f'python "{outside}"',
            "pass\n",
            stale_output=False,
        )
        findings: list[dict[str, object]] = []
        ENGINE.audit_solve(self.root, findings)
        solve_manifest = next(item for item in findings if item["id"] == "SOLVE-002")
        self.assertEqual(solve_manifest["status"], "fail", solve_manifest)
        with self.assertRaisesRegex(ENGINE.EngineError, "绝对路径|未绑定"):
            ENGINE.replay_project(self.root, 30)
        self.assertFalse(list((self.root / "reports").glob("replay_*.json")))

        run_path = self.root / "state" / "run_manifest.json"
        run = ENGINE.read_json(run_path)
        run["command"] = f'"{ENGINE.sys.executable}" work/code/main.py'
        (self.root / "work" / "code" / "main.py").write_text(
            (
                "from pathlib import Path\n"
                "Path('work/results/out.json').write_text('{\\\"value\\\": 1}\\n', encoding='utf-8')\n"
            ),
            encoding="utf-8",
        )
        write_json(run_path, run)
        replay = ENGINE.replay_project(self.root, 30)
        self.assertEqual(replay["outcome"], "PASS", replay)
        self.assertEqual(replay["declared_executable"], ENGINE.sys.executable)

    def test_replay_rejects_undeclared_cache_and_accepts_declared_input(self) -> None:
        source = (
            "from pathlib import Path\n"
            "data = Path('work/results/cache.json').read_bytes()\n"
            "Path('work/results/out.json').write_bytes(data)\n"
        )
        self.make_replay_project("python work/code/main.py", source, stale_output=False)
        cache = self.root / "work" / "results" / "cache.json"
        write_json(cache, {"value": 1})
        with self.assertRaisesRegex(ENGINE.EngineError, "未声明结果/图表"):
            ENGINE.replay_project(self.root, 30)

        declared_input = self.root / "work" / "intake" / "cache.json"
        write_json(declared_input, {"value": 1})
        cache.unlink()
        (self.root / "work" / "results" / "out.json").write_bytes(
            declared_input.read_bytes()
        )
        (self.root / "work" / "code" / "main.py").write_text(
            source.replace("work/results/cache.json", "work/intake/cache.json"),
            encoding="utf-8",
        )
        run_path = self.root / "state" / "run_manifest.json"
        run = ENGINE.read_json(run_path)
        run["declared_inputs"] = ["work/intake/cache.json"]
        write_json(run_path, run)
        replay = ENGINE.replay_project(self.root, 30)
        self.assertEqual(replay["outcome"], "PASS", replay)
        self.assertEqual(replay["declared_inputs"], ["work/intake/cache.json"])

    def test_code_solve_requires_prefreeze_replay(self) -> None:
        source = (
            "from pathlib import Path\n"
            "Path('work/results/out.json').write_text('{\\\"value\\\": 1}\\n', encoding='utf-8')\n"
        )
        self.make_replay_project("python work/code/main.py", source, stale_output=False)
        findings: list[dict[str, object]] = []
        ENGINE.audit_solve(self.root, findings)
        replay_check = next(item for item in findings if item["id"] == "SOLVE-004")
        self.assertEqual(replay_check["status"], "fail", replay_check)
        report = ENGINE.replay_project(self.root, 30)
        self.assertEqual(report["outcome"], "PASS", report)
        findings = []
        ENGINE.audit_solve(self.root, findings)
        replay_check = next(item for item in findings if item["id"] == "SOLVE-004")
        self.assertEqual(replay_check["status"], "pass", replay_check)

    def prepare_no_program_solution(self) -> None:
        self.prepare_intake()
        write_json(
            self.root / "state" / "run_manifest.json",
            {
                "schema_version": 1,
                "program_usage": "none",
                "entrypoint": "",
                "command": "",
                "environment": {},
                "randomness": {"mode": "not_applicable", "seeds": []},
                "declared_inputs": [],
                "official_attachment_inputs": [],
                "expected_outputs": [],
                "manual_replay_procedure": "",
                "no_program_reason": "全部计算均为可人工复核的解析推导。",
            },
        )
        write_json(
            self.root / "state" / "result_ledger.json",
            {
                "schema_version": 1,
                "results": [
                    {
                        "id": "R1",
                        "question_id": "Q1",
                        "name": "解析解",
                        "value": "1/2",
                        "unit": "无量纲",
                        "precision": "exact",
                        "data_scope": "题设常量",
                        "parameter_set": "not_applicable",
                        "random_seed": "not_applicable",
                        "source_object": "paper/equation-Q1",
                        "verification_status": "verified",
                    }
                ],
            },
        )

    def test_no_program_solution_can_pass_solve_audit(self) -> None:
        self.prepare_no_program_solution()
        findings: list[dict[str, object]] = []
        ENGINE.audit_solve(self.root, findings)
        blockers = [item for item in findings if item["status"] == "fail"]
        self.assertFalse(blockers, blockers)
        (self.root / "work" / "code" / "~$book.xlsx").write_bytes(b"office lock")
        findings = []
        ENGINE.audit_solve(self.root, findings)
        blockers = [item for item in findings if item["status"] == "fail"]
        self.assertFalse(blockers, blockers)
        compliance = ENGINE.read_json(
            self.root / "state" / "compliance_attestation.json"
        )
        compliance["support_required"] = False
        compliance["no_support_reason"] = "未使用程序、自主数据、必要中间材料或人工智能明细。"
        compliance["ai_declaration_mode"] = "none"
        write_json(self.root / "state" / "compliance_attestation.json", compliance)
        delivery_findings: list[dict[str, object]] = []
        ENGINE.audit_delivery(self.root, delivery_findings)
        support = next(
            item for item in delivery_findings if item["id"] == "FORMAT-F02"
        )
        self.assertEqual(support["status"], "pass", support)
        (self.root / "work" / "code" / "README.txt").write_text(
            "undeclared artifact\n", encoding="utf-8"
        )
        findings = []
        ENGINE.audit_solve(self.root, findings)
        solve_artifact = next(item for item in findings if item["id"] == "SOLVE-001")
        self.assertEqual(solve_artifact["status"], "fail")

    def test_ai_used_requires_archive_and_allows_subdirectory_member(self) -> None:
        self.prepare_no_program_solution()
        ENGINE.append_chained_event(
            self.root / "state" / "ai_usage_log.jsonl",
            {
                "event_type": "ai_usage",
                "tool": "Codex",
                "model_or_version": "gpt-5",
                "stage": "design",
                "purpose": "候选模型比较",
                "prompt_approach_summary": "比较基线和稳健模型",
                "output_summary": "列出适用条件与风险",
                "adoption_and_modification": "队伍独立验证后重写",
                "manual_verification": "逐项核对公式与假设",
                "supersedes": None,
            },
        )
        detail = self.root / "supporting" / ENGINE.OFFICIAL_AI_DETAIL_NAME
        detail.write_bytes(b"%PDF-1.4\n%AI detail\n")
        manifest = self.root / "supporting" / "file_manifest.json"
        write_json(
            manifest,
            {
                "schema_version": 1,
                "files": [
                    {
                        "path": f"docs/{ENGINE.OFFICIAL_AI_DETAIL_NAME}",
                        "source_path": f"supporting/{ENGINE.OFFICIAL_AI_DETAIL_NAME}",
                        "size": detail.stat().st_size,
                        "sha256": ENGINE.sha256_file(detail),
                    }
                ],
            },
        )
        compliance_path = self.root / "state" / "compliance_attestation.json"
        compliance = ENGINE.read_json(compliance_path)
        compliance.update(
            {
                "support_required": False,
                "ai_declaration_mode": "used",
                "support_manifest": "supporting/file_manifest.json",
            }
        )
        write_json(compliance_path, compliance)
        findings: list[dict[str, object]] = []
        ENGINE.audit_delivery(self.root, findings)
        self.assertEqual(
            next(item for item in findings if item["id"] == "FORMAT-F02")["status"],
            "fail",
        )
        ai_detail = next(item for item in findings if item["id"] == "AI-002")
        self.assertEqual(ai_detail["status"], "fail", ai_detail)
        self.assertFalse(ai_detail["evidence"]["support_archive_contents_ok"])

        archive = self.root / "delivery" / "支撑材料.zip"
        with zipfile.ZipFile(archive, "w") as handle:
            handle.write(detail, f"docs/{ENGINE.OFFICIAL_AI_DETAIL_NAME}")
        compliance.update(
            {
                "support_required": True,
                "support_archive": "delivery/支撑材料.zip",
            }
        )
        compliance["checks"]["archive_contents_checked"] = True
        write_json(compliance_path, compliance)
        findings = []
        ENGINE.audit_delivery(self.root, findings)
        self.assertEqual(
            next(item for item in findings if item["id"] == "FORMAT-F02")["status"],
            "pass",
        )
        self.assertEqual(
            next(item for item in findings if item["id"] == "SUPPORT-001")["status"],
            "pass",
        )
        ai_detail = next(item for item in findings if item["id"] == "AI-002")
        self.assertEqual(ai_detail["status"], "pass", ai_detail)
        self.assertEqual(
            ai_detail["evidence"]["archive_members_with_official_basename"],
            [f"docs/{ENGINE.OFFICIAL_AI_DETAIL_NAME}"],
        )

    def test_support_archive_hash_duplicate_and_traversal_checks(self) -> None:
        source = self.root / "supporting" / "main.py"
        source.write_text("print(1)\n", encoding="utf-8")
        manifest = self.root / "supporting" / "file_manifest.json"
        write_json(
            manifest,
            {
                "schema_version": 1,
                "files": [
                    {
                        "path": "main.py",
                        "source_path": "supporting/main.py",
                        "size": source.stat().st_size,
                        "sha256": ENGINE.sha256_file(source),
                    }
                ]
            },
        )
        archive = self.root / "delivery" / "support.zip"
        with zipfile.ZipFile(archive, "w") as handle:
            handle.writestr("main.py", "tampered\n")
        ok, details = ENGINE.inspect_support_archive(self.root, archive, manifest)
        self.assertFalse(ok)
        self.assertIn("main.py", details["content_mismatches"])

        with zipfile.ZipFile(archive, "w") as handle:
            handle.write(source, "main.py")
            handle.write(source, "MAIN.py")
        ok, details = ENGINE.inspect_support_archive(self.root, archive, manifest)
        self.assertFalse(ok)
        self.assertTrue(details["duplicates"])

        write_json(
            manifest,
            {
                "schema_version": 1,
                "files": [
                    {
                        "path": "../main.py",
                        "source_path": "supporting/main.py",
                        "size": source.stat().st_size,
                        "sha256": ENGINE.sha256_file(source),
                    }
                ]
            },
        )
        with zipfile.ZipFile(archive, "w") as handle:
            handle.write(source, "../main.py")
        ok, details = ENGINE.inspect_support_archive(self.root, archive, manifest)
        self.assertFalse(ok)
        self.assertTrue(details["unsafe"])

    def test_support_archive_must_cover_declared_inputs(self) -> None:
        source = (
            "from pathlib import Path\n"
            "Path('work/results/out.json').write_text('{\\\"value\\\": 1}\\n', encoding='utf-8')\n"
        )
        self.make_replay_project("python work/code/main.py", source, stale_output=False)
        declared_input = self.root / "work" / "intake" / "input.csv"
        declared_input.write_text("x\n1\n", encoding="utf-8")
        run_path = self.root / "state" / "run_manifest.json"
        run = ENGINE.read_json(run_path)
        run["declared_inputs"] = ["work/intake/input.csv"]
        write_json(run_path, run)
        code = self.root / "work" / "code" / "main.py"
        manifest_path = self.root / "supporting" / "file_manifest.json"
        write_json(
            manifest_path,
            {
                "schema_version": 1,
                "files": [
                    {
                        "path": "code/main.py",
                        "source_path": "work/code/main.py",
                        "size": code.stat().st_size,
                        "sha256": ENGINE.sha256_file(code),
                    }
                ],
            },
        )
        archive = self.root / "delivery" / "support.zip"
        with zipfile.ZipFile(archive, "w") as handle:
            handle.write(code, "code/main.py")
        compliance_path = self.root / "state" / "compliance_attestation.json"
        compliance = ENGINE.read_json(compliance_path)
        compliance.update(
            {
                "support_required": True,
                "support_archive": "delivery/support.zip",
                "support_manifest": "supporting/file_manifest.json",
            }
        )
        compliance["checks"]["archive_contents_checked"] = True
        write_json(compliance_path, compliance)
        findings: list[dict[str, object]] = []
        ENGINE.audit_delivery(self.root, findings)
        support = next(item for item in findings if item["id"] == "SUPPORT-001")
        self.assertEqual(support["status"], "fail", support)
        self.assertEqual(
            support["evidence"]["missing_runtime_sources"],
            ["work/intake/input.csv"],
        )

        manifest = ENGINE.read_json(manifest_path)
        manifest["files"].append(
            {
                "path": "data/input.csv",
                "source_path": "work/intake/input.csv",
                "size": declared_input.stat().st_size,
                "sha256": ENGINE.sha256_file(declared_input),
            }
        )
        write_json(manifest_path, manifest)
        with zipfile.ZipFile(archive, "w") as handle:
            handle.write(code, "code/main.py")
            handle.write(declared_input, "data/input.csv")
        findings = []
        ENGINE.audit_delivery(self.root, findings)
        support = next(item for item in findings if item["id"] == "SUPPORT-001")
        self.assertEqual(support["status"], "pass", support)

    def test_zip_safety_limit_has_disclosed_manual_review_fallback(self) -> None:
        self.prepare_no_program_solution()
        first = self.root / "supporting" / "one.txt"
        second = self.root / "supporting" / "two.txt"
        first.write_text("one\n", encoding="utf-8")
        second.write_text("two\n", encoding="utf-8")
        manifest_path = self.root / "supporting" / "file_manifest.json"
        write_json(
            manifest_path,
            {
                "schema_version": 1,
                "files": [
                    {
                        "path": path.name,
                        "source_path": f"supporting/{path.name}",
                        "size": path.stat().st_size,
                        "sha256": ENGINE.sha256_file(path),
                    }
                    for path in (first, second)
                ],
            },
        )
        archive = self.root / "delivery" / "support.zip"
        with zipfile.ZipFile(archive, "w") as handle:
            handle.write(first, first.name)
            handle.write(second, second.name)
        compliance_path = self.root / "state" / "compliance_attestation.json"
        compliance = ENGINE.read_json(compliance_path)
        compliance.update(
            {
                "support_required": True,
                "support_archive": "delivery/support.zip",
                "support_manifest": "supporting/file_manifest.json",
            }
        )
        compliance["checks"]["archive_contents_checked"] = True
        write_json(compliance_path, compliance)
        original_limit = ENGINE.MAX_ARCHIVE_MEMBERS
        try:
            ENGINE.MAX_ARCHIVE_MEMBERS = 1
            findings: list[dict[str, object]] = []
            ENGINE.audit_delivery(self.root, findings)
        finally:
            ENGINE.MAX_ARCHIVE_MEMBERS = original_limit
        support = next(item for item in findings if item["id"] == "SUPPORT-001")
        self.assertEqual(support["status"], "pass", support)
        self.assertTrue(support["evidence"]["safety_limit_exceeded"])
        self.assertTrue(support["evidence"]["manual_attestation_used"])

    def test_managed_path_boundaries_block_unfrozen_evidence(self) -> None:
        self.make_replay_project(
            "python work/code/main.py", self.solver_source(), stale_output=False
        )
        outside = self.root / "misc" / "out.json"
        write_json(outside, {"value": 1})
        run_path = self.root / "state" / "run_manifest.json"
        run = ENGINE.read_json(run_path)
        run["expected_outputs"] = ["misc/out.json"]
        write_json(run_path, run)
        ledger_path = self.root / "state" / "result_ledger.json"
        ledger = ENGINE.read_json(ledger_path)
        ledger["results"][0]["source_file"] = "misc/out.json"
        write_json(ledger_path, ledger)
        findings: list[dict[str, object]] = []
        ENGINE.audit_solve(self.root, findings)
        self.assertEqual(
            next(item for item in findings if item["id"] == "SOLVE-002")["status"],
            "fail",
        )
        self.assertEqual(
            next(item for item in findings if item["id"] == "SOLVE-003")["status"],
            "fail",
        )
        with self.assertRaisesRegex(ENGINE.EngineError, "允许目录"):
            ENGINE.replay_project(self.root, 30)

        (self.root / "paper" / "paper.md").write_text("# paper\n", encoding="utf-8")
        write_json(
            self.root / "state" / "claim_evidence.json",
            {
                "schema_version": 1,
                "claims": [
                    {
                        "id": "C1",
                        "claim": "外部结果",
                        "evidence": [{"type": "data", "ref": "misc/out.json"}],
                    }
                ],
            },
        )
        findings = []
        ENGINE.audit_write(self.root, findings)
        self.assertEqual(
            next(item for item in findings if item["id"] == "WRITE-002")["status"],
            "fail",
        )

        manifest = self.root / "supporting" / "file_manifest.json"
        write_json(
            manifest,
            {
                "schema_version": 1,
                "files": [
                    {
                        "path": "out.json",
                        "source_path": "misc/out.json",
                        "size": outside.stat().st_size,
                        "sha256": ENGINE.sha256_file(outside),
                    }
                ],
            },
        )
        archive = self.root / "delivery" / "support.zip"
        with zipfile.ZipFile(archive, "w") as handle:
            handle.write(outside, "out.json")
        ok, details = ENGINE.inspect_support_archive(self.root, archive, manifest)
        self.assertFalse(ok)
        self.assertTrue(details["source_mismatches"])

    def test_review_finding_requires_exact_schema_and_closes_major(self) -> None:
        self.build_complete_project()
        review_path = self.root / "state" / "reviews" / "model_review.json"
        review = ENGINE.read_json(review_path)
        review["findings"] = [{"severity": "blocker", "status": "fixed"}]
        write_json(review_path, review)
        findings: list[dict[str, object]] = []
        ENGINE.audit_review(self.root, findings)
        review_check = next(item for item in findings if item["id"] == "REVIEW-001")
        self.assertEqual(review_check["status"], "fail", review_check)

        review["findings"] = [
            {
                "id": "MODEL-Q1-001",
                "class": "quality_advisory",
                "severity": "major",
                "status": "open",
                "claim": "稳健性解释不足",
                "evidence": ["paper/paper.md:3"],
                "impact": "结论适用域不清",
                "remediation": "补充适用域说明",
                "owner_stage": "write",
            }
        ]
        write_json(review_path, review)
        findings = []
        ENGINE.audit_review(self.root, findings)
        review_check = next(item for item in findings if item["id"] == "REVIEW-001")
        self.assertEqual(review_check["status"], "fail", review_check)
        review["findings"][0]["status"] = "accepted_risk"
        write_json(review_path, review)
        findings = []
        ENGINE.audit_review(self.root, findings)
        review_check = next(item for item in findings if item["id"] == "REVIEW-001")
        self.assertEqual(review_check["status"], "pass", review_check)

    def test_schema_versions_are_enforced_even_with_recomputed_hashes(self) -> None:
        self.build_complete_project()
        cases = (
            ("state/rules_manifest.json", ENGINE.audit_intake, "RULES-001"),
            ("state/problem_contract.json", ENGINE.audit_intake, "INTAKE-002"),
            ("state/model_contract.json", ENGINE.audit_design, "DESIGN-001"),
            ("state/run_manifest.json", ENGINE.audit_solve, "SOLVE-002"),
            ("state/result_ledger.json", ENGINE.audit_solve, "SOLVE-003"),
            ("state/verification_report.json", ENGINE.audit_verify, "VERIFY-001"),
            ("state/claim_evidence.json", ENGINE.audit_write, "WRITE-002"),
            ("state/reviews/model_review.json", ENGINE.audit_review, "REVIEW-001"),
            (
                "state/compliance_attestation.json",
                ENGINE.audit_delivery,
                "DELIVERY-001",
            ),
        )
        for relative, auditor, finding_id in cases:
            with self.subTest(relative=relative):
                path = self.root / relative
                original_bytes = path.read_bytes()
                original = ENGINE.read_json(path)
                changed = dict(original)
                changed["schema_version"] = 2
                write_json(path, changed)
                findings: list[dict[str, object]] = []
                auditor(self.root, findings)
                finding = next(item for item in findings if item["id"] == finding_id)
                self.assertEqual(finding["status"], "fail", finding)
                path.write_bytes(original_bytes)

        gates_path = self.root / "state" / "human_gates.json"
        original_gates = gates_path.read_bytes()
        gates = ENGINE.read_json(gates_path)
        gates["schema_version"] = 2
        write_json(gates_path, gates)
        self.assertFalse(ENGINE.gate_is_approved(self.root, "submission_lock"))
        gates_path.write_bytes(original_gates)

        decision_path = self.root / "state" / "decision_ledger.jsonl"
        original_decisions = decision_path.read_text(encoding="utf-8")
        decision = json.loads(original_decisions.strip())
        decision["schema_version"] = 2
        decision_body = dict(decision)
        decision_body.pop("event_hash", None)
        decision["event_hash"] = ENGINE.hashlib.sha256(
            ENGINE.canonical_json(decision_body)
        ).hexdigest()
        decision_path.write_text(
            json.dumps(decision, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        ok, errors, _ = ENGINE.verify_event_chain(decision_path)
        self.assertFalse(ok)
        self.assertTrue(any("schema_version" in item for item in errors))
        decision_path.write_text(original_decisions, encoding="utf-8")

        manifest_path = self.root / "supporting" / "file_manifest.json"
        original_manifest = manifest_path.read_bytes()
        manifest = ENGINE.read_json(manifest_path)
        manifest["schema_version"] = 2
        write_json(manifest_path, manifest)
        archive_path = self.root / "delivery" / "支撑材料.zip"
        ok, details = ENGINE.inspect_support_archive(
            self.root, archive_path, manifest_path
        )
        self.assertFalse(ok)
        self.assertTrue(any("schema_version" in item for item in details["manifest_errors"]))
        manifest_path.write_bytes(original_manifest)

        freeze_path = self.root / "state" / "frozen_manifest.json"
        freeze = ENGINE.read_json(freeze_path)
        freeze["schema_version"] = 2
        freeze["manifest_sha256"] = ENGINE.hashlib.sha256(
            ENGINE.canonical_json(
                {key: value for key, value in freeze.items() if key != "manifest_sha256"}
            )
        ).hexdigest()
        write_json(freeze_path, freeze)
        ok, details = ENGINE.verify_freeze(self.root)
        self.assertFalse(ok)
        self.assertFalse(details["schema_valid"])

    def test_decision_event_semantics_are_enforced(self) -> None:
        self.prepare_design()
        decision_path = self.root / "state" / "decision_ledger.jsonl"
        config_path = self.root / "cumcm-project.json"
        original_decision = decision_path.read_bytes()
        original_config = config_path.read_bytes()
        cases = (
            {"event_type": "not-decision"},
            {"impact": ""},
            {"affects_stage": "alien"},
            {"invalidates_from": "submission_lock"},
            {"decided_by": "Codex"},
        )
        for updates in cases:
            with self.subTest(updates=updates):
                decision_path.write_bytes(original_decision)
                config_path.write_bytes(original_config)
                if updates.get("decided_by") == "Codex":
                    config = ENGINE.read_json(config_path)
                    config["mode"] = "competition"
                    write_json(config_path, config)
                rewrite_single_event(decision_path, updates)
                findings: list[dict[str, object]] = []
                ENGINE.audit_design(self.root, findings)
                decision = next(
                    item for item in findings if item["id"] == "DESIGN-002"
                )
                self.assertEqual(decision["status"], "fail", decision)
        decision_path.write_bytes(original_decision)
        config_path.write_bytes(original_config)
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as missing_impact:
                ENGINE.build_parser().parse_args(
                    [
                        "record-decision",
                        str(self.root),
                        "--question",
                        "Q1",
                        "--choice",
                        "A",
                        "--alternatives",
                        "B",
                        "--evidence",
                        "test",
                        "--affects",
                        "design",
                        "--by",
                        "team",
                    ]
                )
        self.assertEqual(missing_impact.exception.code, 2)

    def test_ai_and_change_event_semantics_are_enforced(self) -> None:
        ai_path = self.root / "state" / "ai_usage_log.jsonl"
        ENGINE.append_chained_event(
            ai_path,
            {
                "event_type": "ai_usage",
                "tool": "Codex",
                "model_or_version": "gpt-5",
                "stage": "design",
                "purpose": "比较模型",
                "prompt_approach_summary": "列出候选模型",
                "output_summary": "给出风险",
                "adoption_and_modification": "团队重写",
                "manual_verification": "人工复核",
                "supersedes": None,
            },
        )
        compliance_path = self.root / "state" / "compliance_attestation.json"
        compliance = ENGINE.read_json(compliance_path)
        compliance["ai_declaration_mode"] = "used"
        write_json(compliance_path, compliance)
        original_ai = ai_path.read_bytes()
        for updates in ({"event_type": "other"}, {"stage": "alien"}):
            with self.subTest(ai_updates=updates):
                ai_path.write_bytes(original_ai)
                rewrite_single_event(ai_path, updates)
                findings: list[dict[str, object]] = []
                ENGINE.audit_delivery(self.root, findings)
                ai = next(item for item in findings if item["id"] == "AI-001")
                self.assertEqual(ai["status"], "fail", ai)

        change_path = self.root / "state" / "change_log.jsonl"
        ENGINE.append_chained_event(
            change_path,
            {
                "event_type": "reopen",
                "from_gate": "review_close",
                "reason": "修订论文并重新复核",
                "cleared_gates": ["review_close", "submission_lock"],
                "recorded_by": "engine",
            },
        )
        original_change = change_path.read_bytes()
        invalid_changes = (
            {"event_type": "other"},
            {"from_gate": "alien"},
            {"reason": ""},
            {"cleared_gates": []},
            {"recorded_by": ""},
            {"recorded_by": "not-engine"},
        )
        for updates in invalid_changes:
            with self.subTest(change_updates=updates):
                change_path.write_bytes(original_change)
                rewrite_single_event(change_path, updates)
                findings = []
                ENGINE.audit_delivery(self.root, findings)
                change = next(item for item in findings if item["id"] == "CHANGE-001")
                self.assertEqual(change["status"], "fail", change)

    def test_model_and_none_run_manifest_exact_schema(self) -> None:
        self.prepare_design()
        model_path = self.root / "state" / "model_contract.json"
        original_model = ENGINE.read_json(model_path)
        for invalid_value in (None, "not-an-array", {"Q1": "x"}):
            with self.subTest(global_dependencies=invalid_value):
                model = dict(original_model)
                if invalid_value is None:
                    model.pop("global_dependencies", None)
                else:
                    model["global_dependencies"] = invalid_value
                write_json(model_path, model)
                findings: list[dict[str, object]] = []
                ENGINE.audit_design(self.root, findings)
                check = next(item for item in findings if item["id"] == "DESIGN-001")
                self.assertEqual(check["status"], "fail", check)
        write_json(model_path, original_model)

        self.prepare_no_program_solution()
        run_path = self.root / "state" / "run_manifest.json"
        original_run = ENGINE.read_json(run_path)
        cases = (
            {"entrypoint": r"C:\outside\fake.py"},
            {"command": r"python C:\outside\fake.py"},
            {"__remove__": "declared_inputs"},
            {"__remove__": "official_attachment_inputs"},
        )
        for updates in cases:
            with self.subTest(run_updates=updates):
                run = dict(original_run)
                removed = updates.get("__remove__")
                if removed:
                    run.pop(str(removed), None)
                else:
                    run.update(updates)
                write_json(run_path, run)
                findings = []
                ENGINE.audit_solve(self.root, findings)
                check = next(item for item in findings if item["id"] == "SOLVE-002")
                self.assertEqual(check["status"], "fail", check)
        write_json(run_path, original_run)
        findings = []
        ENGINE.audit_solve(self.root, findings)
        check = next(item for item in findings if item["id"] == "SOLVE-002")
        self.assertEqual(check["status"], "pass", check)

    def test_g1_binds_decision_ledger_and_status_uses_effective_approval(self) -> None:
        self.prepare_design()
        raw_gate = ENGINE.gate_data(self.root)["gates"]["model_contract"]
        self.assertIn("state/decision_ledger.jsonl", raw_gate["evidence_files"])
        ENGINE.append_chained_event(
            self.root / "state" / "decision_ledger.jsonl",
            {
                "event_type": "decision",
                "question_id": "Q1",
                "choice": "保持原模型",
                "alternatives": "无新增替代",
                "evidence": "补充审阅记录",
                "impact": "不改变计算",
                "decided_by": "team",
                "affects_stage": "none",
                "invalidates_from": None,
            },
        )
        self.assertFalse(ENGINE.gate_is_approved(self.root, "model_contract"))
        self.assertTrue(
            ENGINE.gate_data(self.root)["gates"]["model_contract"]["approved"]
        )
        status = ENGINE.project_status(self.root)
        gate = status["gates"]["model_contract"]
        self.assertFalse(gate["approved"])
        self.assertFalse(gate["effective_approved"])
        self.assertTrue(gate["recorded_approved"])

    def test_lock_schema_is_enforced_with_recomputed_hash(self) -> None:
        self.build_complete_project()
        lock_path = self.root / "reports" / "final_lock.json"
        lock = ENGINE.lock_project(self.root)
        lock["schema_version"] = 2
        lock_body = dict(lock)
        lock_body.pop("lock_sha256", None)
        lock["lock_sha256"] = ENGINE.hashlib.sha256(
            ENGINE.canonical_json(lock_body)
        ).hexdigest()
        write_json(lock_path, lock)
        ok, details = ENGINE.verify_lock(self.root)
        self.assertFalse(ok)
        self.assertFalse(details["schema_valid"])

    def test_none_expected_outputs_and_empty_result_values_are_rejected(self) -> None:
        self.prepare_no_program_solution()
        run_path = self.root / "state" / "run_manifest.json"
        run = ENGINE.read_json(run_path)
        run["expected_outputs"] = "work/results/out.json"
        write_json(run_path, run)
        findings: list[dict[str, object]] = []
        ENGINE.audit_solve(self.root, findings)
        self.assertEqual(
            next(item for item in findings if item["id"] == "SOLVE-002")["status"],
            "fail",
        )
        run["expected_outputs"] = []
        write_json(run_path, run)
        ledger_path = self.root / "state" / "result_ledger.json"
        ledger = ENGINE.read_json(ledger_path)
        for empty_value in ([], {}):
            with self.subTest(empty_value=empty_value):
                ledger["results"][0]["value"] = empty_value
                write_json(ledger_path, ledger)
                findings = []
                ENGINE.audit_solve(self.root, findings)
                self.assertEqual(
                    next(item for item in findings if item["id"] == "SOLVE-003")["status"],
                    "fail",
                )

    def test_identity_scanner_reads_docx_and_nested_zip(self) -> None:
        docx = self.root / "paper" / "paper.docx"
        with zipfile.ZipFile(docx, "w") as handle:
            handle.writestr(
                "word/document.xml",
                "<document><t>Example </t><t>University</t></document>",
            )
        inner = self.root / "supporting" / "inner.zip"
        with zipfile.ZipFile(inner, "w") as handle:
            handle.writestr("note.txt", "Example University")
        outer = self.root / "delivery" / "support.zip"
        with zipfile.ZipFile(outer, "w") as handle:
            handle.write(inner, "inner.zip")
        matches = ENGINE.scan_identity_terms(self.root, ["Example University"])
        locations = {item["path"] for item in matches}
        self.assertTrue(any("word/document.xml" in item for item in locations))
        self.assertTrue(any("inner.zip!note.txt" in item for item in locations))

    def test_ephemeral_identity_file_is_excluded_but_real_file_blocks(self) -> None:
        compliance_path = self.root / "state" / "compliance_attestation.json"
        compliance = ENGINE.read_json(compliance_path)
        compliance["forbidden_identity_terms"] = ["张三"]
        compliance["checks"]["anonymous_checked"] = True
        write_json(compliance_path, compliance)
        temporary = self.root / "delivery" / "~$张三.tmp"
        temporary.write_text("张三", encoding="utf-8")
        self.assertTrue(ENGINE.is_ephemeral_file(temporary))
        findings: list[dict[str, object]] = []
        ENGINE.audit_delivery(self.root, findings)
        anonymous = next(item for item in findings if item["id"] == "ANON-001")
        self.assertEqual(anonymous["status"], "pass", anonymous)
        self.assertNotIn(temporary, ENGINE.final_lock_scope(self.root))

        real = self.root / "delivery" / "张三.txt"
        real.write_text("identity", encoding="utf-8")
        findings = []
        ENGINE.audit_delivery(self.root, findings)
        anonymous = next(item for item in findings if item["id"] == "ANON-001")
        self.assertEqual(anonymous["status"], "fail", anonymous)

    def test_rule_classification_separates_internal_evidence(self) -> None:
        report = ENGINE.audit_project(self.root, "delivery", write_report=False)
        by_id = {item["id"]: item for item in report["findings"]}
        self.assertEqual(by_id["RULES-001"]["class"], "project_required")
        self.assertEqual(by_id["AI-001"]["class"], "project_required")
        self.assertEqual(by_id["ANON-002"]["class"], "project_required")
        self.assertEqual(by_id["ANON-001"]["class"], "official_hard")
        self.assertEqual(by_id["FORMAT-F01"]["class"], "official_hard")

    def test_missing_replay_report_blocks_delivery(self) -> None:
        self.build_complete_project()
        for path in (self.root / "reports").glob("replay_*.json"):
            path.unlink()
        report = ENGINE.audit_project(self.root, "delivery", write_report=False)
        replay = next(item for item in report["findings"] if item["id"] == "REPLAY-001")
        self.assertEqual(replay["status"], "fail")
        self.assertEqual(report["outcome"], "FAIL")

    def test_malformed_json_shape_becomes_finding_not_crash(self) -> None:
        write_json(self.root / "state" / "rules_manifest.json", [])
        report = ENGINE.audit_project(self.root, "intake", write_report=False)
        self.assertEqual(report["outcome"], "FAIL")
        self.assertTrue(any(item["id"] == "RULES-001" for item in report["findings"]))

    def test_ai_correction_supersedes_bad_event(self) -> None:
        bad = ENGINE.append_chained_event(
            self.root / "state" / "ai_usage_log.jsonl",
            {
                "event_type": "ai_usage",
                "tool": "Codex",
                "model_or_version": "unspecified",
                "stage": "design",
                "purpose": "模型比较",
                "prompt_approach_summary": "比较三个候选模型",
                "output_summary": "给出优缺点",
                "adoption_and_modification": "团队重写",
                "manual_verification": "人工逐式复核",
                "supersedes": None,
            },
        )
        ENGINE.append_chained_event(
            self.root / "state" / "ai_usage_log.jsonl",
            {
                "event_type": "ai_usage",
                "tool": "Codex",
                "model_or_version": "gpt-5",
                "stage": "design",
                "purpose": "模型比较",
                "prompt_approach_summary": "比较三个候选模型",
                "output_summary": "给出优缺点",
                "adoption_and_modification": "团队重写",
                "manual_verification": "人工逐式复核",
                "supersedes": bad["event_id"],
            },
        )
        compliance = ENGINE.read_json(
            self.root / "state" / "compliance_attestation.json"
        )
        compliance["ai_declaration_mode"] = "used"
        write_json(self.root / "state" / "compliance_attestation.json", compliance)
        findings: list[dict[str, object]] = []
        ENGINE.audit_delivery(self.root, findings)
        ai = next(item for item in findings if item["id"] == "AI-001")
        self.assertEqual(ai["status"], "pass", ai)

    def test_reopen_archives_freeze_and_clears_downstream_gates(self) -> None:
        self.build_complete_project()
        result = ENGINE.reopen_project(
            self.root, "result_freeze", "修正边界条件并重新计算全部结果"
        )
        self.assertFalse((self.root / "state" / "frozen_manifest.json").exists())
        self.assertTrue(result["archived"])
        gates = ENGINE.gate_data(self.root)["gates"]
        self.assertFalse(gates["result_freeze"]["approved"])
        self.assertFalse(gates["review_close"]["approved"])

    def test_delivery_only_reopen_preserves_result_freeze(self) -> None:
        self.build_complete_project()
        ENGINE.lock_project(self.root)
        result = ENGINE.reopen_project(
            self.root, "submission_lock", "仅替换最终提交包并重新完成交付检查"
        )
        self.assertTrue(result["archived"])
        freeze_ok, details = ENGINE.verify_freeze(self.root)
        self.assertTrue(freeze_ok, details)
        self.assertTrue(ENGINE.gate_is_approved(self.root, "result_freeze"))
        self.assertFalse(ENGINE.gate_is_approved(self.root, "submission_lock"))
        _, errors, changes = ENGINE.verify_event_chain(
            self.root / "state" / "change_log.jsonl"
        )
        self.assertFalse(errors)
        self.assertEqual(changes[-1]["recorded_by"], "engine")

    def test_rules_require_exact_complete_2026_official_source_set(self) -> None:
        path = self.root / "state" / "rules_manifest.json"
        rules = ENGINE.read_json(path)
        rules.update(
            {
                "verified_at": "2026-09-10T00:00:00+00:00",
                "verified_by": "team",
                "confirmed_for_year": 2026,
                "sources": [
                    {
                        "id": "fake",
                        "title": "fake",
                        "url": "https://example.invalid/one",
                        "status": "verified",
                    }
                ],
            }
        )
        write_json(path, rules)
        findings: list[dict[str, object]] = []
        ENGINE.audit_intake(self.root, findings)
        check = next(item for item in findings if item["id"] == "RULES-001")
        self.assertEqual(check["status"], "fail", check)
        self.assertEqual(
            set(check["evidence"]["missing_required_sources"]),
            {item["id"] for item in ENGINE.OFFICIAL_2026_SOURCES},
        )

        rules = ENGINE.initial_rules(2026)
        rules.update(
            {
                "verified_at": "2026-09-10T00:00:00+00:00",
                "verified_by": "team",
                "confirmed_for_year": 2026,
            }
        )
        for source in rules["sources"]:
            source["status"] = "verified"
        rules["sources"][0]["url"] = "https://example.invalid/wrong"
        write_json(path, rules)
        findings = []
        ENGINE.audit_intake(self.root, findings)
        check = next(item for item in findings if item["id"] == "RULES-001")
        self.assertEqual(check["status"], "fail", check)
        self.assertEqual(check["evidence"]["url_mismatches"], ["cumcm-2026-rules"])

    def test_replay_report_is_self_hashed_and_bound_to_current_evidence(self) -> None:
        source = (
            "from pathlib import Path\n"
            "Path('work/results/out.json').write_text('{\\\"value\\\": 1}\\n', encoding='utf-8')\n"
        )
        self.make_replay_project("python work/code/main.py", source, stale_output=False)
        report = ENGINE.replay_project(self.root, 30)
        self.assertEqual(report["outcome"], "PASS", report)
        passing, rejected = ENGINE.replay_report_evidence(
            self.root, require_current_freeze=False
        )
        self.assertEqual(len(passing), 1, rejected)

        report_path = self.root / report["report_path"]
        tampered = ENGINE.read_json(report_path)
        tampered["expected_outputs"][0]["size"] += 1
        body = dict(tampered)
        body.pop("report_sha256", None)
        tampered["report_sha256"] = ENGINE.hashlib.sha256(
            ENGINE.canonical_json(body)
        ).hexdigest()
        write_json(report_path, tampered)
        passing, rejected = ENGINE.replay_report_evidence(
            self.root, require_current_freeze=False
        )
        self.assertFalse(passing)
        self.assertIn("output evidence", next(iter(rejected.values())))

    def test_minimal_forged_replay_cannot_approve_result_freeze(self) -> None:
        self.prepare_solve_and_freeze()
        ENGINE.reopen_project(
            self.root, "result_freeze", "测试伪造重放证据是否会被门禁拒绝"
        )
        for path in (self.root / "reports").glob("replay_*.json"):
            path.unlink()
        (self.root / "work" / "code" / "main.py").write_text(
            "pass\n", encoding="utf-8"
        )
        run_path = self.root / "state" / "run_manifest.json"
        fake_path = self.root / "reports" / "replay_forged.json"
        write_json(
            fake_path,
            {
                "schema_version": 1,
                "outcome": "PASS",
                "isolated_workspace": True,
                "clean_workspace": True,
                "returncode": 0,
                "timed_out": False,
                "execution_error": "",
                "expected_outputs": [
                    {
                        "path": "work/results/results.json",
                        "freshly_created": True,
                        "size": 999,
                        "sha256": "0" * 64,
                    }
                ],
                "run_manifest_sha256": ENGINE.sha256_file(run_path),
                "freeze_checked": False,
                "freeze_valid": True,
                "frozen_manifest_sha256": None,
                "unexpected_outputs": [],
                "unexpected_workspace_files": [],
                "runtime_input_drift": [],
                "solve_blockers": [],
            },
        )
        findings: list[dict[str, object]] = []
        ENGINE.audit_solve(self.root, findings)
        replay = next(item for item in findings if item["id"] == "SOLVE-004")
        self.assertEqual(replay["status"], "fail", replay)
        self.assertIn("missing fields", " ".join(next(iter(replay["evidence"]["rejected_reports"].values()))))
        with self.assertRaisesRegex(ENGINE.EngineError, "SOLVE-004"):
            ENGINE.approve_gate(
                self.root, "result_freeze", "team", "伪造报告不得通过 G2"
            )

    def test_external_cmd_cannot_masquerade_as_declared_entrypoint(self) -> None:
        outside = Path(self.temporary.name) / "external.cmd"
        outside.write_text("@echo off\r\nexit /b 0\r\n", encoding="utf-8")
        self.make_replay_project(
            f'"{outside}" work/code/main.py', "pass\n", stale_output=True
        )
        findings: list[dict[str, object]] = []
        ENGINE.audit_solve(self.root, findings)
        check = next(item for item in findings if item["id"] == "SOLVE-002")
        self.assertEqual(check["status"], "fail", check)
        self.assertTrue(
            any("argv[0]" in error for error in check["evidence"]["command_errors"]),
            check,
        )
        with self.assertRaisesRegex(ENGINE.EngineError, r"argv\[0\]"):
            ENGINE.replay_project(self.root, 30)

    def test_official_problem_attachment_is_replayed_but_exempt_from_support(self) -> None:
        source = (
            "from pathlib import Path\n"
            "Path('work/results/out.json').write_bytes(Path('work/intake/official data.csv').read_bytes())\n"
        )
        self.make_replay_project("python work/code/main.py", source, stale_output=False)
        official = self.root / "work" / "intake" / "official data.csv"
        official.write_text('{"value": 1}\n', encoding="utf-8")
        run_path = self.root / "state" / "run_manifest.json"
        run = ENGINE.read_json(run_path)
        run["declared_inputs"] = ["work/intake/official data.csv"]
        run["official_attachment_inputs"] = [
            {
                "path": "work/intake/official data.csv",
                "source_ref": "2026 A题官方附件 data.csv",
            }
        ]
        write_json(run_path, run)
        replay = ENGINE.replay_project(self.root, 30)
        self.assertEqual(replay["outcome"], "PASS", replay)

        code = self.root / "work" / "code" / "main.py"
        manifest_path = self.root / "supporting" / "file_manifest.json"
        write_json(
            manifest_path,
            {
                "schema_version": 1,
                "files": [
                    {
                        "path": "code/main.py",
                        "source_path": "work/code/main.py",
                        "size": code.stat().st_size,
                        "sha256": ENGINE.sha256_file(code),
                    }
                ],
            },
        )
        archive = self.root / "delivery" / "support.zip"
        with zipfile.ZipFile(archive, "w") as handle:
            handle.write(code, "code/main.py")
        compliance_path = self.root / "state" / "compliance_attestation.json"
        compliance = ENGINE.read_json(compliance_path)
        compliance.update(
            {
                "support_required": True,
                "support_archive": "delivery/support.zip",
                "support_manifest": "supporting/file_manifest.json",
                "ai_declaration_mode": "none",
            }
        )
        compliance["checks"]["archive_contents_checked"] = True
        write_json(compliance_path, compliance)
        findings: list[dict[str, object]] = []
        ENGINE.audit_delivery(self.root, findings)
        support = next(item for item in findings if item["id"] == "SUPPORT-001")
        self.assertEqual(support["status"], "pass", support)
        self.assertEqual(support["evidence"]["missing_runtime_sources"], [])
        self.assertEqual(
            support["evidence"]["official_attachment_exemptions"],
            run["official_attachment_inputs"],
        )

        run["official_attachment_inputs"][0]["source_ref"] = ""
        write_json(run_path, run)
        findings = []
        ENGINE.audit_solve(self.root, findings)
        check = next(item for item in findings if item["id"] == "SOLVE-002")
        self.assertEqual(check["status"], "fail", check)

    def test_undeclared_result_or_figure_breaks_output_closure(self) -> None:
        source = (
            "from pathlib import Path\n"
            "Path('work/results/out.json').write_text('{\\\"value\\\": 1}\\n', encoding='utf-8')\n"
        )
        self.make_replay_project("python work/code/main.py", source, stale_output=False)
        ENGINE.replay_project(self.root, 30)
        (self.root / "work" / "figures" / "key.svg").write_text(
            "<svg xmlns='http://www.w3.org/2000/svg'/>", encoding="utf-8"
        )
        findings: list[dict[str, object]] = []
        ENGINE.audit_solve(self.root, findings)
        check = next(item for item in findings if item["id"] == "SOLVE-002")
        self.assertEqual(check["status"], "fail", check)
        self.assertEqual(
            check["evidence"]["undeclared_output_artifacts"],
            ["work/figures/key.svg"],
        )

    def test_windows_quoted_input_and_py_version_selector_replay(self) -> None:
        command = 'python work/code/main.py --input="work/intake/data file.csv"'
        argv, errors = ENGINE.parse_command(command)
        self.assertFalse(errors, errors)
        self.assertEqual(argv[-1], "--input=work/intake/data file.csv")
        source = (
            "from pathlib import Path\n"
            "Path('work/results/out.json').write_text('{\\\"value\\\": 1}\\n', encoding='utf-8')\n"
        )
        self.make_replay_project(command, source, stale_output=False)
        data = self.root / "work" / "intake" / "data file.csv"
        data.write_text("x\n1\n", encoding="utf-8")
        run_path = self.root / "state" / "run_manifest.json"
        run = ENGINE.read_json(run_path)
        run["declared_inputs"] = ["work/intake/data file.csv"]
        write_json(run_path, run)
        report = ENGINE.replay_project(self.root, 30)
        self.assertEqual(report["outcome"], "PASS", report)

        for path in (self.root / "reports").glob("replay_*.json"):
            path.unlink()
        run["command"] = 'py -3.12 work/code/main.py --input="work/intake/data file.csv"'
        write_json(run_path, run)
        report = ENGINE.replay_project(self.root, 30)
        self.assertEqual(report["outcome"], "PASS", report)
        self.assertEqual(report["resolved_command"][0], ENGINE.sys.executable)
        self.assertNotIn("-3.12", report["resolved_command"])

    def test_any_project_code_artifact_can_be_declared_as_entrypoint(self) -> None:
        source = (
            "from pathlib import Path\n"
            "Path('work/results/out.json').write_text('{\\\"value\\\": 1}\\n', encoding='utf-8')\n"
        )
        self.make_replay_project("python work/code/model.custom", source, stale_output=False)
        main = self.root / "work" / "code" / "main.py"
        custom = self.root / "work" / "code" / "model.custom"
        custom.write_bytes(main.read_bytes())
        main.unlink()
        run_path = self.root / "state" / "run_manifest.json"
        run = ENGINE.read_json(run_path)
        run["entrypoint"] = "work/code/model.custom"
        write_json(run_path, run)
        report = ENGINE.replay_project(self.root, 30)
        self.assertEqual(report["outcome"], "PASS", report)
        findings: list[dict[str, object]] = []
        ENGINE.audit_solve(self.root, findings)
        by_id = {item["id"]: item for item in findings}
        self.assertEqual(by_id["SOLVE-001"]["status"], "pass", by_id["SOLVE-001"])
        self.assertEqual(by_id["SOLVE-002"]["status"], "pass", by_id["SOLVE-002"])

    def test_support_manifest_types_and_zip_special_members_are_rejected(self) -> None:
        source = self.root / "supporting" / "one-byte.txt"
        source.write_bytes(b"x")
        manifest = self.root / "supporting" / "file_manifest.json"
        archive = self.root / "delivery" / "support.zip"
        base_item = {
            "path": "one-byte.txt",
            "source_path": "supporting/one-byte.txt",
            "size": 1,
            "sha256": ENGINE.sha256_file(source),
        }
        with zipfile.ZipFile(archive, "w") as handle:
            handle.write(source, "one-byte.txt")
        for update in ({"size": True}, {"purpose": ""}, {"purpose": 1}):
            with self.subTest(update=update):
                item = dict(base_item)
                item.update(update)
                write_json(manifest, {"schema_version": 1, "files": [item]})
                ok, details = ENGINE.inspect_support_archive(
                    self.root, archive, manifest
                )
                self.assertFalse(ok, details)
                self.assertTrue(details["manifest_errors"], details)

        link_payload = b"one-byte.txt"
        source.write_bytes(link_payload)
        link_item = {
            "path": "link",
            "source_path": "supporting/one-byte.txt",
            "size": len(link_payload),
            "sha256": ENGINE.hashlib.sha256(link_payload).hexdigest(),
        }
        write_json(manifest, {"schema_version": 1, "files": [link_item]})
        info = zipfile.ZipInfo("link")
        info.create_system = 3
        info.external_attr = (ENGINE.stat.S_IFLNK | 0o777) << 16
        with zipfile.ZipFile(archive, "w") as handle:
            handle.writestr(info, link_payload)
        ok, details = ENGINE.inspect_support_archive(self.root, archive, manifest)
        self.assertFalse(ok, details)
        self.assertEqual(details["special_members"], ["link"])

    def test_support_false_rejects_declared_or_unexpected_archive(self) -> None:
        self.prepare_no_program_solution()
        compliance_path = self.root / "state" / "compliance_attestation.json"
        compliance = ENGINE.read_json(compliance_path)
        compliance.update(
            {
                "support_required": False,
                "no_support_reason": "未使用程序、自主数据、必要中间材料或人工智能明细。",
                "support_archive": "",
                "ai_declaration_mode": "none",
            }
        )
        write_json(compliance_path, compliance)
        findings: list[dict[str, object]] = []
        ENGINE.audit_delivery(self.root, findings)
        check = next(item for item in findings if item["id"] == "FORMAT-F02")
        self.assertEqual(check["status"], "pass", check)

        archive = self.root / "delivery" / "unexpected.zip"
        with zipfile.ZipFile(archive, "w") as handle:
            handle.writestr("note.txt", "unexpected")
        findings = []
        ENGINE.audit_delivery(self.root, findings)
        check = next(item for item in findings if item["id"] == "FORMAT-F02")
        self.assertEqual(check["status"], "fail", check)
        self.assertEqual(
            check["evidence"]["delivery_archives"],
            ["delivery/unexpected.zip"],
        )

    def test_freeze_and_lock_reject_noncanonical_hash_rows(self) -> None:
        self.build_complete_project()
        freeze_path = self.root / "state" / "frozen_manifest.json"
        original_freeze = freeze_path.read_bytes()
        freeze = ENGINE.read_json(freeze_path)
        freeze["files"][0]["size"] = True
        freeze["manifest_sha256"] = ENGINE.hashlib.sha256(
            ENGINE.canonical_json(
                {key: value for key, value in freeze.items() if key != "manifest_sha256"}
            )
        ).hexdigest()
        write_json(freeze_path, freeze)
        ok, details = ENGINE.verify_freeze(self.root)
        self.assertFalse(ok, details)
        self.assertFalse(details["manifest_well_formed"])
        freeze_path.write_bytes(original_freeze)

        lock_path = self.root / "reports" / "final_lock.json"
        lock = ENGINE.lock_project(self.root)
        lock["files"][0]["size"] = True
        body = dict(lock)
        body.pop("lock_sha256", None)
        lock["lock_sha256"] = ENGINE.hashlib.sha256(
            ENGINE.canonical_json(body)
        ).hexdigest()
        write_json(lock_path, lock)
        ok, details = ENGINE.verify_lock(self.root)
        self.assertFalse(ok, details)
        self.assertFalse(details["manifest_well_formed"])

    def test_self_sourced_data_requires_support_even_without_program(self) -> None:
        self.prepare_no_program_solution()
        data_path = self.root / "work" / "intake" / "self-sourced.csv"
        data_path.write_text("x\n1\n", encoding="utf-8")
        problem_path = self.root / "state" / "problem_contract.json"
        problem = ENGINE.read_json(problem_path)
        problem["data_inventory"] = [
            {
                "id": "D1",
                "description": "队伍自主查阅并用于解析计算的数据",
                "origin": "self_sourced",
                "used": True,
                "path": "work/intake/self-sourced.csv",
                "source_ref": "公开数据页 2026-09-10 下载",
            }
        ]
        write_json(problem_path, problem)
        compliance_path = self.root / "state" / "compliance_attestation.json"
        compliance = ENGINE.read_json(compliance_path)
        compliance.update(
            {
                "support_required": False,
                "no_support_reason": "声称没有任何需要提交的支撑材料。",
                "support_archive": "",
                "support_manifest": "",
                "ai_declaration_mode": "none",
            }
        )
        write_json(compliance_path, compliance)
        findings: list[dict[str, object]] = []
        ENGINE.audit_delivery(self.root, findings)
        check = next(item for item in findings if item["id"] == "FORMAT-F02")
        self.assertEqual(check["status"], "fail", check)
        self.assertEqual(
            check["evidence"]["self_sourced_used_paths"],
            ["work/intake/self-sourced.csv"],
        )

        manifest_path = self.root / "supporting" / "file_manifest.json"
        write_json(
            manifest_path,
            {
                "schema_version": 1,
                "files": [
                    {
                        "path": "data/self-sourced.csv",
                        "source_path": "work/intake/self-sourced.csv",
                        "size": data_path.stat().st_size,
                        "sha256": ENGINE.sha256_file(data_path),
                    }
                ],
            },
        )
        archive = self.root / "delivery" / "support.zip"
        with zipfile.ZipFile(archive, "w") as handle:
            handle.write(data_path, "data/self-sourced.csv")
        compliance.update(
            {
                "support_required": True,
                "no_support_reason": "",
                "support_archive": "delivery/support.zip",
                "support_manifest": "supporting/file_manifest.json",
            }
        )
        compliance["checks"]["archive_contents_checked"] = True
        write_json(compliance_path, compliance)
        findings = []
        ENGINE.audit_delivery(self.root, findings)
        support = next(item for item in findings if item["id"] == "SUPPORT-001")
        self.assertEqual(support["status"], "pass", support)
        self.assertEqual(support["evidence"]["missing_runtime_sources"], [])

    def test_interactive_mode_requires_hashed_pre_and_post_freeze_records(self) -> None:
        self.prepare_design()
        workbook = self.root / "work" / "code" / "model.xlsx"
        with zipfile.ZipFile(workbook, "w") as handle:
            handle.writestr("[Content_Types].xml", "<Types/>")
        write_json(self.root / "work" / "results" / "results.json", {"estimate": 1.25})
        write_json(
            self.root / "state" / "run_manifest.json",
            {
                "schema_version": 1,
                "program_usage": "interactive",
                "entrypoint": "work/code/model.xlsx",
                "command": "",
                "environment": {
                    "software": "Microsoft Excel",
                    "version": "2026",
                    "dependencies": "Solver add-in",
                },
                "randomness": {"mode": "not_applicable", "seeds": []},
                "declared_inputs": [],
                "official_attachment_inputs": [],
                "expected_outputs": ["work/results/results.json"],
                "manual_replay_procedure": (
                    "1. 在独立空白目录打开 model.xlsx 并启用 Solver；"
                    "2. 按工作表说明重新计算并导出 work/results/results.json。"
                ),
                "no_program_reason": "",
            },
        )
        write_json(
            self.root / "state" / "result_ledger.json",
            {
                "schema_version": 1,
                "results": [
                    {
                        "id": "R1",
                        "question_id": "Q1",
                        "name": "目标量估计",
                        "value": 1.25,
                        "unit": "无量纲",
                        "precision": 0.01,
                        "data_scope": "测试数据",
                        "parameter_set": "default",
                        "random_seed": "not_applicable",
                        "source_file": "work/results/results.json",
                        "verification_status": "verified",
                    }
                ],
            },
        )
        checks = [
            {"type": "dimension_or_unit", "status": "pass", "evidence": "单位复核"},
            {"type": "boundary_or_invariant", "status": "pass", "evidence": "边界复核"},
            {"type": "independent_evidence", "status": "pass", "evidence": "人工复算"},
            {"type": "uncertainty_or_robustness", "status": "pass", "evidence": "扰动检查"},
        ]
        write_json(
            self.root / "state" / "verification_report.json",
            {"schema_version": 1, "questions": {"Q1": {"checks": checks}}},
        )
        findings: list[dict[str, object]] = []
        ENGINE.audit_solve(self.root, findings)
        self.assertEqual(
            next(item for item in findings if item["id"] == "SOLVE-004")["status"],
            "fail",
        )
        args = SimpleNamespace(
            root=str(self.root),
            performed_by="队员A",
            workspace="另一份只含交付工件的独立干净目录",
            notes="逐步操作后重新导出的结果与项目当前结果完全一致。",
            confirm_clean_workspace=True,
            confirm_inputs_unchanged=True,
            confirm_outputs_regenerated=True,
        )
        pre = ENGINE.command_record_manual_replay(args)
        self.assertFalse(pre["freeze_checked"])
        findings = []
        ENGINE.audit_solve(self.root, findings)
        self.assertEqual(
            next(item for item in findings if item["id"] == "SOLVE-004")["status"],
            "pass",
        )
        ENGINE.approve_gate(
            self.root, "result_freeze", "team", "simulation interactive result review"
        )
        ENGINE.freeze_project(self.root)
        post = ENGINE.command_record_manual_replay(args)
        self.assertTrue(post["freeze_checked"])
        compliance_path = self.root / "state" / "compliance_attestation.json"
        compliance = ENGINE.read_json(compliance_path)
        compliance["checks"]["support_replayed"] = True
        write_json(compliance_path, compliance)
        findings = []
        ENGINE.audit_delivery(self.root, findings)
        replay = next(item for item in findings if item["id"] == "REPLAY-001")
        self.assertEqual(replay["status"], "pass", replay)

        post_path = self.root / post["report_path"]
        tampered = ENGINE.read_json(post_path)
        tampered["expected_outputs"][0]["sha256"] = "0" * 64
        write_json(post_path, tampered)
        findings = []
        ENGINE.audit_delivery(self.root, findings)
        replay = next(item for item in findings if item["id"] == "REPLAY-001")
        self.assertEqual(replay["status"], "fail", replay)

        run_path = self.root / "state" / "run_manifest.json"
        run = ENGINE.read_json(run_path)
        run["expected_outputs"] = ["work/results/missing.json"]
        write_json(run_path, run)
        findings = []
        ENGINE.audit_solve(self.root, findings)
        solve = next(item for item in findings if item["id"] == "SOLVE-002")
        self.assertEqual(solve["status"], "fail", solve)

    def test_reopen_rejects_damaged_change_log_before_mutation(self) -> None:
        self.build_complete_project()
        gates_path = self.root / "state" / "human_gates.json"
        freeze_path = self.root / "state" / "frozen_manifest.json"
        before_gates = gates_path.read_bytes()
        before_freeze = freeze_path.read_bytes()
        (self.root / "state" / "change_log.jsonl").write_text(
            "{broken json\n", encoding="utf-8"
        )
        with self.assertRaisesRegex(ENGINE.EngineError, "回退日志已有损坏"):
            ENGINE.reopen_project(self.root, "result_freeze", "需要重新检查全部结果")
        self.assertEqual(gates_path.read_bytes(), before_gates)
        self.assertEqual(freeze_path.read_bytes(), before_freeze)

    def test_rules_and_problem_schema_are_strict_about_required_fields_and_booleans(self) -> None:
        self.prepare_intake()
        rules_path = self.root / "state" / "rules_manifest.json"
        rules = ENGINE.read_json(rules_path)
        rules.pop("notes")
        write_json(rules_path, rules)
        findings: list[dict[str, object]] = []
        ENGINE.audit_intake(self.root, findings)
        self.assertEqual(
            next(item for item in findings if item["id"] == "RULES-001")["status"],
            "fail",
        )
        self.verify_rules()
        problem_path = self.root / "state" / "problem_contract.json"
        problem = ENGINE.read_json(problem_path)
        problem["schema_version"] = True
        write_json(problem_path, problem)
        findings = []
        ENGINE.audit_intake(self.root, findings)
        self.assertEqual(
            next(item for item in findings if item["id"] == "INTAKE-002")["status"],
            "fail",
        )

    def test_run_environment_and_nonapplicable_fields_are_strict(self) -> None:
        self.prepare_solve_and_freeze()
        run_path = self.root / "state" / "run_manifest.json"
        run = ENGINE.read_json(run_path)
        for updates in (
            {"environment": {"dependencies": "standard-library"}},
            {"manual_replay_procedure": 1},
            {"no_program_reason": "not applicable"},
        ):
            with self.subTest(updates=updates):
                candidate = dict(run)
                candidate.update(updates)
                write_json(run_path, candidate)
                findings: list[dict[str, object]] = []
                ENGINE.audit_solve(self.root, findings)
                check = next(item for item in findings if item["id"] == "SOLVE-002")
                self.assertEqual(check["status"], "fail", check)

    def test_boolean_schema_versions_are_rejected_in_jsonl_and_support_manifest(self) -> None:
        event_path = self.root / "state" / "decision_ledger.jsonl"
        ENGINE.append_chained_event(
            event_path,
            {
                "event_type": "decision",
                "question_id": "Q1",
                "choice": "A",
                "alternatives": "B",
                "evidence": "test",
                "impact": "test",
                "decided_by": "team",
                "affects_stage": "design",
                "invalidates_from": "model_contract",
            },
        )
        rewrite_single_event(event_path, {"event_id": "not-a-uuid"})
        ok, errors, _ = ENGINE.verify_event_chain(event_path)
        self.assertFalse(ok)
        self.assertTrue(any("UUID" in error for error in errors), errors)
        rewrite_single_event(event_path, {"schema_version": True})
        ok, errors, _ = ENGINE.verify_event_chain(event_path)
        self.assertFalse(ok)
        self.assertTrue(any("schema_version" in error for error in errors), errors)

        source = self.root / "supporting" / "source.txt"
        source.write_text("x", encoding="utf-8")
        archive = self.root / "delivery" / "support.zip"
        with zipfile.ZipFile(archive, "w") as handle:
            handle.write(source, "source.txt")
        manifest = self.root / "supporting" / "file_manifest.json"
        write_json(
            manifest,
            {
                "schema_version": True,
                "files": [
                    {
                        "path": "source.txt",
                        "source_path": "supporting/source.txt",
                        "size": 1,
                        "sha256": ENGINE.sha256_file(source),
                    }
                ],
            },
        )
        ok, details = ENGINE.inspect_support_archive(self.root, archive, manifest)
        self.assertFalse(ok, details)
        self.assertTrue(details["manifest_errors"], details)

    def test_gate_approval_requires_true_boolean_and_iso_timestamp(self) -> None:
        self.prepare_intake()
        ENGINE.approve_gate(
            self.root, "problem_selection", "team", "simulation problem review"
        )
        gate_path = self.root / "state" / "human_gates.json"
        original = ENGINE.read_json(gate_path)
        for updates in (
            {"approved": 1},
            {"approved_at": "not-an-iso-time"},
        ):
            with self.subTest(updates=updates):
                candidate = json.loads(json.dumps(original))
                candidate["gates"]["problem_selection"].update(updates)
                write_json(gate_path, candidate)
                self.assertFalse(
                    ENGINE.gate_is_approved(self.root, "problem_selection")
                )


if __name__ == "__main__":
    unittest.main()

# 项目工件精确字段

本文只在创建或修改相应 JSON 工件时读取。除支撑清单的 `path` 专指归档内成员路径外，所有文件路径均以项目根目录为基准，必须是项目内相对路径；不得使用盘符绝对路径、`..` 越界或符号链接。`schema_version` 当前为整数 `1`，JSON boolean `true` 不视为 `1`。以下“必需”指当前引擎审计所需字段；可以添加项目自身所需的额外字段，但不得改变必需字段语义。

## `state/rules_manifest.json`

顶层必需 `schema_version=1`、`competition="CUMCM"`、整数 `year`、非空 ISO-8601 `verified_at`、非空 `verified_by`、与 `year` 相同的 `confirmed_for_year`、非空 `sources`、数组 `region_rules`、对象 `classification` 和文本 `notes`。`sources[]` 每项至少含唯一非空 `id`、非空 `title/url` 与 `status="verified"`；只有实际打开来源核对后才可改为 `verified`。

2026 项目必须同时保留且不得改写 URL 的三个来源 ID：

- `cumcm-2026-rules` → `https://www.mcm.edu.cn/html_cn/node/9d8e511fe7a1447b35f53a82c908e2e0.html`
- `cumcm-2026-format` → `https://www.mcm.edu.cn/html_cn/node/4cd596519c9eb9fbd866398f6df0caa3.html`
- `cumcm-2026-ai` → `https://www.mcm.edu.cn/html_cn/node/fef94648f2836ab6cc81586f4c38512b.html`

可以增加赛区或当届补充来源，但单个其他网页不能替代上述必需集合。

## `state/problem_contract.json`

顶层必需非空 `problem_code/problem_title/problem_group`，以及 `questions`、`data_inventory`、`unknowns`、`assumptions_to_test` 和 `risk_register`。后五项均为数组；`questions` 与 `risk_register` 必须非空。每个问题对象至少含唯一非空 `id`、非空 `task/output`，以及由非空文本组成的数组 `inputs/depends_on`。`depends_on` 只能引用已登记问题，不能自依赖或形成环。风险项可先用非空文本或非空项目自定义 object，随后再细化触发条件、影响和退路。

`data_inventory[]` 每项必须含唯一非空 `id`、非空 `description`、`origin`、boolean `used`、字符串 `path/source_ref`。`origin` 只能为 `official_problem/self_sourced/generated/none`。实际使用的 `official_problem/self_sourced` 必须给出 `work/intake/` 下现存普通文件和非空来源；其中 `self_sourced+used=true` 会强制 `support_required=true` 并要求该源文件进入支撑清单/归档。`origin=none` 时必须 `used=false` 且 `path/source_ref` 为空。不能用自由文本清单掩盖数据来源。

## `state/model_contract.json`

顶层 `questions` 为按问题 ID 索引的 object，并覆盖问题合同全部 ID；`global_dependencies` 为数组。每个问题合同必须含非空 `baseline/main_model/fallback`，以及均由非空文本组成的非空数组 `assumptions/validation`。这里审计的是论证角色和验证计划，不要求堆叠三个复杂模型。

## `state/run_manifest.json`

顶层必需字段：

| 字段 | 类型 | 规则 |
|---|---|---|
| `schema_version` | integer | 当前为 `1` |
| `program_usage` | string | `code`、`interactive` 或 `none` |
| `entrypoint` | string | `code/interactive` 时为 `work/code/` 下已存在的项目内入口；`none` 时必须为空字符串 |
| `command` | string | `code` 时非空，且参数中必须实际绑定 `entrypoint`；不得通过绝对/越界参数、内联求值或模块模式改跑另一入口 |
| `environment` | object | `code` 时至少含一个非空运行时键（如 `python/r/julia/matlab/runtime/interpreter/compiler/software`）；`interactive` 时至少含非空 `software/version`；全部键和值须有意义；`none` 时精确为空对象 |
| `randomness` | object | `mode` 必须为 `deterministic`、`seeded` 或 `not_applicable`；`seeds` 必须为列表，`seeded` 时不得为空 |
| `declared_inputs` | array of strings | 洁净重放所需的项目输入；每项为 `work/intake`、`work/modeling` 或 `work/code` 下已存在的普通文件；不得与输出重叠；`none` 时必须为空 |
| `official_attachment_inputs` | array of objects | 赛题官方提供、重放需要但按官方规范无需重复收入支撑包的附件；每项必须且只能含 `path/source_ref`，`path` 位于 `work/intake` 且也列入 `declared_inputs`，`source_ref` 精确记录题号与官方附件名；`none` 时必须为空 |
| `expected_outputs` | array of strings | `code/interactive` 时非空，每项为本次运行新生成且位于 `work/results` 或 `work/figures` 的普通文件；`none` 时必须为空 |
| `manual_replay_procedure` | string | `interactive` 时至少 40 字符并以换行或分号分成至少两步，写明从原始输入到预期输出的操作；`code/none` 时为空 |
| `no_program_reason` | string | `none` 时非空，且 `work/code/` 不得留程序或交互工件 |

`program_usage=code` 时 `manual_replay_procedure/no_program_reason` 必须为空；`interactive` 时 `command/no_program_reason` 必须为空，入口必须是非空、签名可识别的受支持交互工件；`program_usage=none` 时不得保留伪入口或伪命令：`entrypoint/command/manual_replay_procedure` 必须为空，`environment={}`，`randomness={"mode":"not_applicable","seeds":[]}`，且 `declared_inputs/official_attachment_inputs/expected_outputs` 均为空。表中所有顶层字段即使取空值也必须存在。

最小形状：

```json
{
  "schema_version": 1,
  "program_usage": "code",
  "entrypoint": "work/code/main.py",
  "command": "python work/code/main.py",
  "environment": {"python": "3.12", "dependencies": "requirements.txt"},
  "randomness": {"mode": "seeded", "seeds": [2026]},
  "declared_inputs": ["work/intake/problem-data.csv"],
  "official_attachment_inputs": [
    {"path": "work/intake/problem-data.csv", "source_ref": "2026 A题官方附件 problem-data.csv"}
  ],
  "expected_outputs": ["work/results/results.json"],
  "manual_replay_procedure": "",
  "no_program_reason": ""
}
```

`replay` 仅适用于 `program_usage=code`。它新建空白运行目录，只复制 `work/code/` 的全部非临时文件和 `declared_inputs`，以空的 `work/results/`、`work/figures/` 启动；未声明缓存不会被带入。执行后必须恰好生成 `expected_outputs`，不得新增其他结果、修改代码/输入或写入运行范围外文件；重生成文件还必须逐项匹配项目当前输出，冻结后再匹配冻结清单。`work/results` 与 `work/figures` 的全部非临时普通文件必须恰好闭包于 `expected_outputs`，不能把未声明的旧图或中间结果用于 Claim–Evidence。G2 前至少运行一次，冻结后再次运行，最终交付只接受与当前入口、命令、运行文件、输入、输出、引擎文件、`run_manifest` 和 `frozen_manifest` 全部一致的后冻结报告。

`interactive` 不伪装成自动执行。队员在独立干净副本按步骤实际操作后，必须用 `record-manual-replay` 显式确认干净目录、输入未变和输出已重新生成；该命令将入口、环境、步骤、运行文件、输入、逐项输出、执行人、观察说明、引擎及 run/freeze 哈希写成自哈希报告。G2 前记录一次，冻结后在支撑包副本上再做一次；最终交付只接受与当前冻结一致的后冻结人工报告。它是结构化队伍自证，不是引擎自动启动 Excel/SPSS，也不证明软件许可证或外部环境可用。

命令的 `argv[0]` 只能是引擎允许的解释器/建模运行器，或项目内已声明入口；项目外任意 `.exe/.cmd/.bat` 不能用“把入口当作无效参数”来绕过。绝对路径只允许用于受信运行器，脚本、工作簿和文件参数仍必须留在项目契约内。引擎以 `shell=False` 调用子进程，但 Windows 可能由操作系统按文件关联处理项目内 `.bat/.cmd`；这不等于进程安全隔离。

洁净副本不是操作系统安全沙箱：它不主动提供未声明项目文件，但无法阻止受信任脚本自行访问网络、系统文件、用户目录或已安装包。因此只运行队伍信任的代码；`environment` 仍须完整记录外部软件与依赖。

## `state/result_ledger.json`

顶层为 `{"schema_version": 1, "results": [...]}`。`results` 必须非空，`id` 唯一，并覆盖 `problem_contract.questions[]` 中的每个问题 ID。每个结果对象必需：

| 字段 | 类型 | 规则 |
|---|---|---|
| `id` | non-empty string | 全账本唯一的结果 ID |
| `question_id` | non-empty string | 必须对应问题合同中的 ID |
| `name` | non-empty string | 结果名称 |
| `value` | non-null, non-empty JSON value | 数值、文本、对象或指向长数组的摘要；不得含 `NaN/Infinity` |
| `unit` | non-empty string | 无量纲时也要显式写明 |
| `precision` | positive finite number or non-empty string | 例如 `0.01`、`"exact"`、`"3 significant digits"` |
| `data_scope` | non-empty string | 数据时间、空间、样本或子集范围 |
| `parameter_set` | non-empty string | 参数集、配置 ID 或 `"not_applicable"` |
| `random_seed` | non-empty string | 实际种子文本或 `"not_applicable"` |
| `verification_status` | non-empty string | 候选结果可用 `candidate`；进入结果冻结前必须为 `verified` |

来源字段至少一个非空：

- `source_file`：项目内已存在文件；
- `source_object`：程序对象、工作簿单元格/区域或数据集字段标识；
- `generation_command`：可重现该结果的命令或操作标识。

`program_usage=code/interactive` 时，每条结果都必须有 `source_file`，且该路径必须逐字出现在 `run_manifest.expected_outputs` 中，以保证自动或人工重放实际重新生成论文引用的结果。`program_usage=none` 时可只用 `source_object` 或 `generation_command` 记录解析推导来源。

## `state/verification_report.json`

顶层必须是 `{"schema_version":1,"questions":{...}}`，`questions` 以问题合同中的每个问题 ID 为键且不得漏项。每个问题对象至少含 `checks` 数组。每条 check 至少含：

| 字段 | 类型 | 规则 |
|---|---|---|
| `type` | string | `dimension_or_unit`、`boundary_or_invariant`、`independent_evidence`、`uncertainty_or_robustness` 之一；每问四类均须有有效记录 |
| `status` | string | `pass` 或 `not_applicable` |
| `evidence` | string | `status=pass` 时为非空、可定位证据 |
| `rationale` | string | `status=not_applicable` 时为非空理由；不能用空白 N/A 绕过 |

可以为同一类型增加多条检验及项目字段。进入冻结前，`result_ledger.results[*].verification_status` 必须全部为 `verified`。

## `state/claim_evidence.json`

顶层为 `{"schema_version": 1, "claims": [...]}`，`claims` 必须非空，且每条 claim 的 `id` 在全文件唯一。每条 claim 必需：

```json
{
  "id": "C-Q1-01",
  "claim": "关键结论文本",
  "evidence": [
    {"type": "result", "ref": "R-Q1-EST"},
    {"type": "figure", "ref": "work/figures/q1.svg"},
    {"type": "literature", "ref": "doi:10.xxxx/example"}
  ]
}
```

`evidence` 为非空 object 列表，仅允许：

- `type=result`：`ref` 必须是 `result_ledger` 中已存在的结果 ID；
- `type=figure/table/code/data`：`ref` 必须是项目内已存在文件；
- `type=literature/official_rule`：`ref` 必须是非空的 DOI、URL、引用键或规则标识。

若 `program_usage=code/interactive`，任何位于 `work/results` 或 `work/figures` 的文件都必须列入 `run_manifest.expected_outputs` 并进入重放闭环；不能用一个已冻结但未声明、未重生成的旧文件支撑 claim。确属人工生成的证据应放在适当的 `paper/` 或 `supporting/` 路径，清楚记录来源，而不是伪装成程序输出。

## `state/reviews/*.json`

固定文件和角色映射：

| 文件 | `reviewer_role` |
|---|---|
| `state/reviews/model_review.json` | `model` |
| `state/reviews/repro_review.json` | `repro` |
| `state/reviews/judge_review.json` | `judge` |

每份报告必需：

| 字段 | 类型 | 规则 |
|---|---|---|
| `schema_version` | integer | 当前为 `1` |
| `status` | string | 完成审查时为 `completed` |
| `reviewer_role` | string | 必须与文件名映射一致 |
| `independent_context` | boolean | 必须为 `true`；无法真隔离时不得伪造为 `true` |
| `scope` | non-empty string or array | 本席审查范围 |
| `evidence_examined` | non-empty array | 实际打开的文件、页码、结果 ID 或命令 |
| `findings` | array | 可为空，但范围、证据和结论不得为空 |
| `conclusion` | non-empty string | 独立审查结论 |

`findings[]` 的 `id` 必须在单份报告内唯一，并严格使用 [review-rubric.md](review-rubric.md) 的结构：`id`、`class`、`severity`、`status`、`claim`、`evidence`、`impact`、`remediation`、`owner_stage`；其中 `evidence` 是非空文本数组。其状态为 `open/fixed/accepted_risk/not_applicable`，与引擎审计状态 `pass/fail/review/not_applicable` 不同。任何 `severity=blocker` 必须 `fixed`；`severity=major` 不得保持 `open`；`class=official_hard` 只能 `fixed` 或有证据地 `not_applicable`。

## `state/compliance_attestation.json`

顶层字段固定语义如下：

| 字段 | 类型 | 规则 |
|---|---|---|
| `schema_version` | integer | 当前为 `1` |
| `final_paper` | string | `delivery/` 下唯一最终 `.pdf/.docx/.doc` 的相对路径 |
| `support_required` | boolean | 有程序/交互工件、自主使用数据、必要大篇幅中间材料或 AI 明细时为 `true`；确无任何应交材料时才为 `false` |
| `no_support_reason` | string | `support_required=false` 时至少 12 字符，说明为何没有程序、交互、自主数据、必要中间材料或 AI 明细；为 `true` 时必须为空 |
| `support_archive` | string | `support_required=true` 时为 `delivery/` 下唯一 ZIP/RAR；为 `false` 时必须为空且 `delivery/` 不得另有 ZIP/RAR |
| `support_manifest` | string | 支撑清单路径，通常为 `supporting/file_manifest.json` |
| `ai_declaration_mode` | string | 只能是 `used` 或 `none`，必须与活动 AI 日志一致 |
| `ai_detail_pdf` | string | `used` 时指向 `supporting/AI工具使用详情.pdf` |
| `forbidden_identity_terms` | non-empty array of strings | 队员姓名、学校全称/简称、赛区等本队已知身份词 |
| `checks` | object | 下列人工确认键均存在，交付时按适用规则设为 `true` |

`checks` 的官方事项键：`paper_and_print_match`、`abstract_page_checked`、`body_page_limit_checked`、`anonymous_checked`、`citations_checked`、`appendix_checked`、`ai_declaration_checked`、`ai_usage_truth_confirmed`。项目复核键：`official_rules_rechecked_on_submission_day`、`final_render_checked`；有支撑材料时还须 `archive_contents_checked`，`code/interactive` 时还须 `support_replayed`。布尔勾选是团队自证，不替代实际逐页/解压检查。

## `supporting/file_manifest.json`

顶层为 `{"schema_version": 1, "files": [...]}`。需要支撑材料时 `files` 必须非空，并与归档中的普通文件集合完全一致。每项必需：

| 字段 | 类型 | 规则 |
|---|---|---|
| `path` | non-empty string | 归档内成员路径；不允许绝对路径、盘符、`..`、NUL 或不区分大小写的重复路径 |
| `source_path` | non-empty string | 对应该成员的项目内原始证据路径，以项目根目录为基准，例如 `work/code/main.py` |
| `size` | non-negative integer（不能是 boolean） | 项目源文件和归档成员必须同时等于该字节数 |
| `sha256` | string | 项目源文件和归档成员必须同时匹配该 64 位十六进制 SHA-256 |

示例：

```json
{
  "schema_version": 1,
  "files": [
    {
      "path": "code/main.py",
      "source_path": "work/code/main.py",
      "size": 1234,
      "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    }
  ]
}
```

`purpose` 是可选字段，但出现时必须是非空文本。ZIP 模式会同时比较项目源文件、清单和压缩包成员的路径、大小和哈希，并拒绝符号链接、设备文件等非普通成员；RAR 需人工完成同等检查并保留证据。`program_usage=code/interactive` 时，`source_path` 集合必须覆盖 `work/code/` 下全部非临时普通文件以及全部非官方附件的 `declared_inputs`，不能只列入口；`data_inventory` 中实际使用的自主数据也必须覆盖，即使 `program_usage=none`。`official_attachment_inputs` 仍进入洁净重放，但依据 2026 官方“赛题原始数据除外”不强制重复收入支撑包；团队必须为每项填写可核对的 `source_ref`，引擎不认证附件来源真伪。`__pycache__`、`.pyc/.pyo`、Office 临时锁文件和系统缩略图不属于提交工件。使用 AI 时，某个归档成员的 basename 必须精确为 `AI工具使用详情.pdf`，可以位于归档子目录；该项 `source_path` 必须对应项目中的 `supporting/AI工具使用详情.pdf`。使用 AI 时不得设置 `support_required=false`。

为防 ZIP bomb，内置自动检查上限为 10,000 个成员或 200,000,000 字节解压后总大小；这不是官方格式规则。超过上限的官方合规 ZIP 不会被断言违规，但必须像 RAR 一样由团队完成清单、源文件和归档内容的人工复核并勾选 `archive_contents_checked`。

## 哈希链 JSONL 事件

三份 JSONL 都只能追加，不能改旧行。公共必需字段为：`schema_version=1`、唯一 UUID 文本 `event_id`、ISO-8601 `timestamp`、首行为 `GENESIS`/后续为前条哈希的 `previous_hash`，以及对“除自身外整条 canonical JSON”计算的 64 位小写 `event_hash`。

`state/decision_ledger.jsonl` 的每条活动事件还必须含：

- `event_type="decision"`；
- 已登记的 `question_id`；
- 非空 `choice/alternatives/evidence/impact/decided_by`；
- `affects_stage` 为 `intake/design/solve/verify/write/review/delivery/none`；
- `invalidates_from` 必须精确等于该阶段映射的门禁：`problem_selection/model_contract/result_freeze/result_freeze/review_close/review_close/submission_lock/null`。

`state/ai_usage_log.jsonl` 的每条事件还必须含：`event_type="ai_usage"`，非空 `tool/model_or_version/purpose/prompt_approach_summary/output_summary/adoption_and_modification/manual_verification`，`stage` 为七阶段之一，`supersedes` 为 `null` 或已存在的前序 AI `event_id`。被后续有效事件 supersede 的旧行仍留在哈希链，但不作为活动披露记录。

`state/change_log.jsonl` 只由 `reopen` 追加：`event_type="reopen"`、`from_gate` 为五门禁之一、非空 `reason`、`cleared_gates` 精确等于从该门禁起的后缀列表，且 `recorded_by` 必须精确为 `"engine"`。它不进入结果冻结，但最终交付审计验证其完整链，最终锁覆盖该文件。

## `state/human_gates.json`

顶层为 `schema_version=1` 和 `gates`。`gates` 含 `problem_selection/model_contract/result_freeze/review_close/submission_lock` 五项，每项字段为：

```json
{
  "approved": true,
  "approved_by": "队员标识",
  "approved_at": "2026-09-10T00:00:00+00:00",
  "approval_kind": "team_attested",
  "note": "团队实际复核说明",
  "evidence_sha256": "64位小写SHA-256",
  "evidence_files": ["state/...", "work/..."]
}
```

`approved` 必须是 JSON boolean，不能用 `1` 代替；已批准项的 `approved_at` 必须是含时区的 ISO-8601。`training` 的有效批准使用 `approval_kind="simulation"`，`competition` 使用 `team_attested`；未批准项以上字段除 `approved=false/evidence_files=[]` 外可为 `null`。读取批准时复算证据清单摘要，任一内容或集合漂移都会使批准无效。该记录是队伍自证，不是身份认证或数字签名。

## `state/frozen_manifest.json` 与 `reports/final_lock.json`

`freeze` 生成的冻结文件必需且只由引擎写入：

```json
{
  "schema_version": 1,
  "created_at": "ISO-8601",
  "algorithm": "sha256",
  "files": [{"path": "...", "size": 123, "sha256": "64位小写SHA-256"}],
  "manifest_sha256": "对移除本字段后的整个对象计算的SHA-256"
}
```

`lock` 生成的最终锁包含 `schema_version=1`、ISO-8601 `locked_at`、`algorithm="sha256"`、`audit_outcome="PASS"`、固定作用域文本数组 `scope`、非空 `files` 哈希清单，以及对移除自身后的对象计算的 `lock_sha256`。冻结与最终锁的每个 file row 都恰含项目内相对 `path`、非负整数 `size` 和 64 位小写 `sha256`；校验会比较缺失、内容变化和作用域新增文件。

这些清单能发现意外漂移，但本地拥有者可以重算普通 SHA-256；它们不是受信第三方时间戳或不可抵赖签名。

## `reports/replay_*.json`

报告只由 `replay` 生成。当前 schema 必须恰好包含以下字段，缺少或增加字段都不作为有效门禁证据：

- 身份与时间：`schema_version`、ISO-8601 `started_at/finished_at`、`declared_entrypoint`、`declared_command`、`declared_executable`、字符串数组 `resolved_command`；
- 洁净输入：`isolated_workspace=true`、`clean_workspace=true`、`runtime_files`、逐项 `path/size/sha256` 的 `runtime_evidence`、`declared_inputs`、`official_attachment_inputs`；
- 执行状态：正整数 `timeout_seconds`、`timed_out=false`、空 `execution_error`、整数 `returncode=0`、文本 `stdout_tail/stderr_tail`；
- 输出闭包：逐项恰含 `path/freshly_created=true/size/sha256` 的 `expected_outputs`，以及必须为空的 `project_output_mismatches/unexpected_outputs/unexpected_workspace_files/runtime_input_drift/solve_blockers`；
- 绑定与结论：`run_manifest_sha256`、`frozen_manifest_sha256`、布尔 `freeze_checked/freeze_valid`、对象 `freeze_details`、当前 `engine_sha256`、`outcome="PASS"`、与实际文件一致的 `report_path`；
- 自校验：`report_sha256`，即对移除该字段后的整个报告计算的 SHA-256。

审计会把 `runtime_files/runtime_evidence`、官方附件声明和每个输出的路径/大小/哈希与当前项目重新计算结果逐项比较；最终交付还要求后冻结报告与当前冻结清单逐项相同。自哈希与引擎哈希可发现手工删字段、普通篡改和旧版本报告，但仍不是敌对本地拥有者无法伪造的数字签名；`competition` 的真实性继续由参赛队负责。

## `reports/manual_replay_*.json`

仅由 `record-manual-replay` 为 `interactive` 模式生成，并恰含：`schema_version/recorded_at/performed_by/workspace_description/notes/procedure/declared_entrypoint/environment`，三个必须为 `true` 的确认 `isolated_workspace/inputs_unchanged/outputs_regenerated`，`runtime_files/runtime_evidence/declared_inputs/official_attachment_inputs/expected_outputs`，当前 `run_manifest_sha256/frozen_manifest_sha256/freeze_checked/freeze_valid/engine_sha256`，以及 `outcome="PASS"/report_path/report_sha256`。报告会逐项绑定当前文件的路径、大小和 SHA-256；`competition` 执行人不能写成 AI/Agent。预冻结和后冻结各记录一次，交付只接受当前冻结有效的后冻结报告。该报告记录真实人工动作的责任链，但仍是队伍自证，不是自动化软件可用性证明或第三方签名。

## `reports/audit_*.json`

每次累计审计包含 `schema_version=1`、`generated_at`、目标 `stage`、累计 `scope`、`outcome=PASS|FAIL`、`summary`、免责声明 `claim` 和 `findings`。Finding 使用引擎状态 `pass/fail/review/not_applicable`；它与三席报告内部 finding 状态不同。审计报告由命令重建，不手工改成 PASS。

# 引擎架构与状态协议

## 目标

把一次 CUMCM 项目表示为可审计的状态机，而不是一组散落的对话、脚本和论文文件。Agent 可以生成、计算和审查，但参赛队对选题、模型合同、冻结结果和最终提交承担批准责任。

## 状态机

```text
rules/intake -> design -> solve -> verify/freeze -> write -> review -> delivery/lock
      G0          G1                       G2                 G3          G4
```

- 阶段可以向前推进，也可以因证据变化而回退。
- 全流程共七阶段、五个人工门禁 G0–G4。任何上游证据变化都应使相关下游批准失效。
- `competition` 模式下，G0–G4 只能在参赛队明确确认后记录；Agent 不能自批。`approve` 保存的是队伍自证（`team_attested`），只拒绝明显的 AI/Agent 批准人名并检查前置审计；它不验证现实身份、签名或三名队员在场，不得对外宣称为身份认证。
- `training` 模式可模拟批准，但 `approval_kind` 必须是 `simulation`。
- 每个批准同时保存该门禁累计证据清单 `evidence_files` 及其清单摘要 `evidence_sha256`。G1 起绑定完整决策账本；后续读取门禁时会重新计算。内容、文件集合或路径发生漂移，批准即视为无效，必须按变更协议重审。`status.gates[*].approved/effective_approved` 显示当前有效状态，`recorded_approved` 只保留历史记录含义。
- 最终锁定不是“文件只读”的替代品，而是一份可复核的 SHA-256 清单。

## 项目目录

`init` 创建最小目录和空账本，不创建伪造的结果或论文：

```text
project/
|-- cumcm-project.json
|-- state/
|   |-- rules_manifest.json
|   |-- problem_contract.json
|   |-- model_contract.json
|   |-- run_manifest.json
|   |-- result_ledger.json
|   |-- verification_report.json
|   |-- claim_evidence.json
|   |-- compliance_attestation.json
|   |-- human_gates.json
|   |-- decision_ledger.jsonl
|   |-- ai_usage_log.jsonl
|   |-- change_log.jsonl
|   `-- reviews/
|-- work/
|   |-- intake/
|   |-- modeling/
|   |-- code/
|   |-- results/
|   `-- figures/
|-- paper/
|-- supporting/
|-- delivery/
`-- reports/
```

## 账本语义

创建或编辑 `rules_manifest`、`run_manifest`、`result_ledger`、`verification_report`、`claim_evidence`、`compliance_attestation`、三席报告、JSONL 事件或支撑材料清单前，读取 [artifact-schemas.md](artifact-schemas.md)。冻结、重放、审计和最终锁也在该文件列出完整生成字段。本文仅保留语义和状态规则。

### rules_manifest

记录当届官方来源、发布日期、最后核验时间和每条规则的等级。来源只有在实际打开并核对后才可从 `unverified` 改成 `verified`。至少区分：

- `official_hard`：组委会/赛区当届文件明确要求，违反可能取消资格。
- `project_required`：本引擎为可复现和一致性设置的门禁，不宣称是官方规定。
- `quality_advisory`：提高获奖概率的建议，可基于题型说明理由后偏离。

### problem_contract

至少包含：

- `problem_code`、`problem_title`、`problem_group`；
- `questions[]`：`id`、原始要求、输入、输出、评价判据和与其他问题的依赖；
- `data_inventory[]`：以结构化 `origin/used/path/source_ref` 区分赛题附件、自主数据、派生数据和无数据；自主查阅且实际使用的文件会被交付审计强制收入支撑包；
- `unknowns[]`、`assumptions_to_test[]`、`risk_register[]`。

### model_contract

按问题 ID 记录：

- `baseline`：最低复杂度、可解释且能独立跑通的参照；
- `main_model`：最终主方案及其机制/统计依据；
- `fallback`：数据、收敛或识别失败时的退路；
- `variables`、`assumptions`、`objective_or_likelihood`、`constraints`；
- `validation`：量纲、边界、独立复算、对照、敏感性/稳健性；
- `handoff`：向下游问题传递的值、不确定性和适用域。

### run_manifest

`program_usage` 必须在三种模式中选一：

- `code`：有可自动运行的项目内入口和绑定该入口的命令。`declared_inputs` 显式列出除代码外所需的项目输入；其中赛题官方附件同时登记在 `official_attachment_inputs`，用于重放但不强制重复提交。`replay` 从空白目录只复制全部代码与这些输入，再生成精确声明且与项目当前输出一致的结果/图表。`work/results` 与 `work/figures` 必须完全闭包于 `expected_outputs`。G2 前的 PASS 证明洁净可运行，冻结后的第二次 PASS 还要逐项匹配冻结输出；最终交付只接受与当前入口、运行文件、引擎、`run_manifest/frozen_manifest` 全部一致的报告。`argv[0]` 只能是允许的解释器/建模运行器或项目内声明入口，不能用项目外可执行文件忽略入口参数。该机制不携带作者缓存，但不是操作系统进程沙箱，不能禁止受信任脚本自行访问网络、用户目录、系统文件或已安装依赖。
- `interactive`：使用 Excel/SPSS/MATLAB Live Script 等交互工件，登记有签名的非空入口、`software/version`、预期输出和至少两步的人工重放步骤。队员在独立副本实际复现后用 `record-manual-replay` 写入逐项文件哈希、执行人和观察；G2 前、冻结后各一次。引擎核对报告与当前 run/freeze/输出，但不会假装自动操作外部软件。
- `none`：确实未使用程序或交互软件，不留程序工件，并在 `no_program_reason` 说明。重放检查记为 `not_applicable`。

### decision_ledger

每条 JSONL 事件应包含：`event_id`、`timestamp`、`question_id`、`choice`、`alternatives`、`evidence`、`impact`、`decided_by`、`affects_stage`、`invalidates_from`、`previous_hash`、`event_hash`。使用 `record-decision --affects` 标明变更影响的最早阶段；需要时由引擎撤销相关门禁。修改旧决定时追加新事件，不重写历史。

### result_ledger

每条结果至少包含：

- `id`、`question_id`、`name`、`value`、`unit`、`precision`；
- `source_file`、`source_object` 或生成命令；
- `data_scope`、`parameter_set`、`random_seed`；
- `verification_status` 和关联验证项。

可把长数组保存在 CSV/XLSX/JSON 中，账本只登记文件、字段和哈希，不复制大量数据。

### ai_usage_log

只记录真实发生的事件：工具/模型、阶段、用途、主要提示思路、输出摘要、采用与修改、人工验证。语言润色可按官方规则简化“采用与验证”细节，但仍要记录工具和用途。写错时追加完整新事件，以 `supersedes` 指向一个已存在的前序 AI `event_id`；旧事件保留在哈希链中但不再作为活动披露记录。不得随机生成、补写不存在的典型对话或自动宣称“团队主导”。

### human_gates 与 change_log

`state/human_gates.json` 的每个 G0–G4 条目由 `approve` 写入 `approved`、`approved_by`、`approved_at`、`approval_kind`、`note`、`evidence_sha256` 和 `evidence_files`。不得手工复制批准；门禁读取会复算证据摘要，漂移即自动失效。

`reopen` 撤销指定门禁及下游批准、归档失效的冻结/重放/最终锁后，只向 `state/change_log.jsonl` 追加事件。事件包含 `event_id`、时间戳、`event_type=reopen`、`from_gate`、`reason`、`cleared_gates`、精确的 `recorded_by="engine"`、`previous_hash` 和 `event_hash`。该日志不进入结果冻结范围，避免“记录一次合法回退”本身造成新冻结漂移；最终交付审计仍验证其哈希链，最终锁也覆盖它。

## 哈希与冻结

`freeze` 覆盖：

- `cumcm-project.json`
- `work/intake/`
- `work/modeling/`
- `work/code/`
- `work/results/`
- `work/figures/`
- `state/rules_manifest.json`
- `state/problem_contract.json`
- `state/model_contract.json`
- `state/decision_ledger.jsonl`
- `state/run_manifest.json`
- `state/result_ledger.json`
- `state/verification_report.json`

所有文件使用 SHA-256。冻结清单同时记录文件大小和相对路径。后续审计既检查已冻结文件是否变更/缺失，也检查冻结范围是否出现未登记的新文件。`state/change_log.jsonl` 明确不在结果冻结范围中。

图片的哈希只能证明文件没变，不能证明图中数字正确；图表数据必须来自结果账本或可重放脚本。普通 SHA-256 清单和重放报告自哈希用于发现漂移与不完整证据，不构成第三方签名，也不能对敌对的项目本地拥有者提供不可抵赖认证。

`lock` 与上述结果冻结不同：最终锁覆盖 `cumcm-project.json`、`state/**`、`work/**`、`paper/**`、`supporting/**`、`delivery/**`、`reports/audit_*.json`、`reports/replay_*.json` 和 `reports/manual_replay_*.json`。这是完整证据包；任何缺失、新增或哈希变化都会使最终锁失效。Python 字节码/`__pycache__`、Office 临时锁文件、系统缩略图等已知非提交临时文件不进入证据范围；`reports/history/**` 和 `reports/final_lock.json` 自身也不在其自身哈希列表中。

## 变更协议

冻结后发现错误时：

1. 在决策账本追加变更事件，写明原因、受影响问题和证据。
2. 执行 `reopen --from result_freeze --reason "..."`；引擎撤销 G2 及下游门禁、归档旧冻结/重放/最终锁，并向 `state/change_log.jsonl` 追加哈希链事件。
3. 修改代码或数据处理，完整重跑受影响问题及依赖问题。
4. 更新结果账本和验证报告，重新审计、人工批准并冻结。
5. 重新生成受影响的图、表、正文和 Claim–Evidence 映射。

不得直接手改论文数字、冻结清单或审计报告来“消除”差异。

## 审计结果

每个 finding 具有：

- `id`：稳定检查编号；
- `class`：`official_hard`、`project_required` 或 `quality_advisory`；
- `status`：`pass`、`fail`、`review` 或 `not_applicable`；
- `message`、`evidence`、`remediation`。

`pass` 表示当前可判定检查通过；`fail` 表示已确定不合格；`review` 表示存在例如 20 MB 十进制/二进制界线这类必须在提交系统或最新通知中解决的歧义，在解决前仍计为 `BLOCKER`；`not_applicable` 表示有证据地不适用，按通过处理。`official_hard` 和 `project_required` 的 `fail/review` 均为 `BLOCKER`。`quality_advisory` 只警告，不通过固定分数或奖项概率制造伪精确结论。注意：三席报告内部的 `open/fixed/accepted_risk/not_applicable` 是另一套 finding 闭环状态，见 [artifact-schemas.md](artifact-schemas.md)。

## CLI 状态变更

以下命令假定已按 `SKILL.md` 从已加载文件的绝对路径得到 `$CumcmEngine`。不得在项目当前目录直接使用相对的 `scripts/cumcm_engine.ps1`。

```powershell
# 初始化（已有 cumcm-project.json 或任何托管目录都会拒绝覆盖）
& $CumcmEngine init "D:\contest\A" --year 2026 --mode competition

# 审计：默认累计检查当前阶段及其上游
& $CumcmEngine audit "D:\contest\A" --stage verify

# 决定变更必须标明最早影响阶段
& $CumcmEngine record-decision "D:\contest\A" --question Q2 --choice "..." --alternatives "..." --evidence "..." --impact "..." --affects design --by "队员A"

# G2 前先在洁净副本重放，证明统一入口可从声明输入生成结果
& $CumcmEngine replay "D:\contest\A" --timeout 600

# interactive 模式改为队员在独立目录实际操作后记录结构化人工重放
& $CumcmEngine record-manual-replay "D:\contest\A" --by "队员A" --workspace "独立干净副本 D:\replay\A" --notes "重新导出结果并逐项核对一致" --confirm-clean-workspace --confirm-inputs-unchanged --confirm-outputs-regenerated

# 团队批准 G2 并冻结；competition 模式必须提供可追溯说明
& $CumcmEngine approve "D:\contest\A" --gate result_freeze --by "队员A" --note "三名队员复核记录 2026-09-12 21:30"
& $CumcmEngine freeze "D:\contest\A"

# 冻结后再执行适用模式的同一重放命令，使报告绑定当前冻结证据
& $CumcmEngine replay "D:\contest\A" --timeout 600
& $CumcmEngine status "D:\contest\A"

# 有证据变化时撤销下游门禁
& $CumcmEngine reopen "D:\contest\A" --from result_freeze --reason "Q2 边界条件修正"

# 交付审计通过后生成最终锁定
& $CumcmEngine lock "D:\contest\A"
```

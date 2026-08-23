---
name: cumcm-competition-engine
description: 面向全国大学生数学建模竞赛（CUMCM、数学建模国赛、高教社杯）的专项作战与审计引擎。用于选题、问题拆解、模型合同、代码求解、结果冻结、国赛论文、三席复核、支撑材料和 AI 使用合规；不用于 MCM/ICM 或普通学术论文。
metadata:
  short-description: CUMCM 国赛专项作战与审计
---

# CUMCM 国赛专项作战审计引擎

以“可解释的建模决策、可复现的数值证据、可追溯的论文结论、可核验的合规交付”为唯一终点。质量优先，不以最快生成完整答案为目标。

本技能是 CUMCM 总控。现有 `math-modeling` 只作为算法、历年优秀论文和文档工具的资源库；Nature 系列技能只在明确的专业环节受控接入，不能接管国赛论文结构或改写已冻结事实。

## 适用边界

- 仅用于 CUMCM/全国大学生数学建模竞赛/数学建模国赛/高教社杯。
- MCM/ICM、一般建模项目使用 `math-modeling`；普通科研论文使用相应 Nature 学术技能。
- 不依赖 DSH、私有工作流运行时、个人绝对路径或某台机器上的缓存。
- 不把字体、行距、摘要字符数、固定图表数量、所谓“AI 率”或 AI 检测器结果写成官方硬规则。
- 竞赛期间不得代替参赛队与队外人员交流，不检索或传播当届赛题的现成解答；AI 仅作允许范围内的辅助，并如实记录、逐项人工复核。

## 首次进入项目

1. 确认比赛名称、届次、题目/附件、当前阶段，以及是 `competition` 还是 `training` 模式。信息可从已有文件可靠推断时直接推断并记录，不重复询问。
2. 读取 [references/official-rules.md](references/official-rules.md)，通过当届组委会官网重新核验规则；历史模板和优秀论文不能覆盖当届规则。
3. 读取 [references/architecture.md](references/architecture.md)。创建或修改 `run_manifest`、`result_ledger`、`claim_evidence`、三席报告或支撑材料清单时，再按需读取 [references/artifact-schemas.md](references/artifact-schemas.md)。
4. 从本轮已加载的 `SKILL.md` **实际绝对路径**解析包装器；不得从项目当前目录猜测 `scripts/`：

   ```powershell
   # 将 skill loader 已读取的 SKILL.md 绝对路径填入此变量；不要把占位文字原样执行
   $CumcmSkillFile = '<已加载 SKILL.md 的绝对路径>'
   $CumcmEngine = (Resolve-Path -LiteralPath (Join-Path (Split-Path -Parent $CumcmSkillFile) 'scripts\cumcm_engine.ps1')).Path

   # Windows 优先使用绝对包装器路径，它会避开 Windows Store 的空 python 占位符
   & $CumcmEngine init "<项目目录>" --year <年份> --mode competition
   ```

5. 执行 `status` 和当前阶段的 `audit`。已有本引擎项目不得重新初始化；若目标目录尚无 `cumcm-project.json` 但已有 `state/work/paper/supporting/delivery/reports` 任一托管路径，`init` 也会拒绝覆盖，须先人工盘点并迁移到新项目骨架。已初始化项目应读取现有账本并从最近一个未通过门禁继续。

## 两种模式

- `competition`（默认）：五个人工门禁 G0–G4 必须由参赛队明确批准。Agent 不得替队伍自批，也不得把沉默视为批准；命令仅记录队伍自证，不构成身份认证。每次批准同时绑定当时的 `evidence_sha256/evidence_files`，证据内容或集合漂移后该批准自动失效。
- `training`：允许完整回放与模拟门禁，但审批记录必须写明 `simulation`，输出不得冒充真实参赛决策。

## 单一事实源

所有工作都围绕项目账本推进，禁止靠聊天记忆传递关键事实：

- `state/rules_manifest.json`：当届规则来源、核验日期和规则等级。
- `state/problem_contract.json`：题意、问题链、输入输出、数据和风险。
- `state/model_contract.json`：各问基线模型、主模型、备选方案、假设与验证计划。
- `state/decision_ledger.jsonl`：关键选择、备选、依据、影响和批准人。
- `state/result_ledger.json`：论文可引用的结果、单位、来源脚本和验证状态。
- `state/ai_usage_log.jsonl`：实际 AI 使用记录；不得赛后虚构交互。
- `state/frozen_manifest.json`：规则、问题/模型合同、决策、输入、代码、结果、图和验证账本的哈希快照。
- `state/claim_evidence.json`：论文结论到结果、图表、代码和文献的映射。
- `state/human_gates.json`：G0–G4 的队伍自证、批准说明及其证据摘要。
- `state/change_log.jsonl`：只由 `reopen` 追加的哈希链式回退记录；不进入结果冻结，但在最终交付审计和锁定中核验。
- `reports/`：阶段审计报告和最终锁定清单。

数值、单位、术语、图表编号和结论以账本为准。结果冻结后如需修改，先记录变更原因，撤销下游门禁，再重新求解、验证和冻结；禁止只改论文中的数字。

## 七阶段主流程

每个阶段开始时读取 [references/stage-contracts.md](references/stage-contracts.md) 对应章节。阶段结束运行累计审计；存在 `BLOCKER` 时不得进入下一阶段。

| 阶段 | 核心产物 | 人工门禁 |
|---|---|---|
| 00 规则与选题 | 规则清单、题目包、问题依赖图、数据清单、风险表 | G0 `problem_selection` |
| 10 模型设计 | 每问的 baseline/main/fallback、假设、公式、验证与全局依赖 | G1 `model_contract` |
| 20 求解实现 | `code/interactive/none` 模式、重放入口或说明、结果与账本 | 无新门禁 |
| 30 独立验证 | 量纲/边界/复算/敏感性/稳健性报告、哈希冻结 | G2 `result_freeze` |
| 40 论文构建 | Claim–Evidence 映射、国赛中文论文、图表、引用 | 无新门禁 |
| 50 三席复核 | 建模席、复现席、评阅席报告和闭环问题单 | G3 `review_close` |
| 60 合规交付 | 匿名检查、论文、适用的支撑材料或无材料声明、AI 声明、最终清单 | G4 `submission_lock` |

常用命令：

```powershell
& $CumcmEngine status "<项目目录>"
& $CumcmEngine audit "<项目目录>" --stage design
& $CumcmEngine record-decision "<项目目录>" --question Q1 --choice "..." --alternatives "..." --evidence "..." --impact "..." --affects design --by "<队员标识>"
& $CumcmEngine record-ai "<项目目录>" --tool "Codex" --model "<实际模型或版本>" --stage design --purpose "..." --prompt-summary "..." --output-summary "..." --adoption "..." --verification "..."
& $CumcmEngine approve "<项目目录>" --gate model_contract --by "<队员标识>" --note "<可追溯的真实复核说明>"
& $CumcmEngine freeze "<项目目录>"
& $CumcmEngine replay "<项目目录>" --timeout 600
& $CumcmEngine record-manual-replay "<项目目录>" --by "<队员标识>" --workspace "<独立干净副本说明>" --notes "<实际重放观察>" --confirm-clean-workspace --confirm-inputs-unchanged --confirm-outputs-regenerated
& $CumcmEngine lock "<项目目录>"
```

`record-decision --affects` 必须标明新决定影响的最早阶段（`intake/design/solve/verify/write/review/delivery/none`）。AI 记录写错时不改旧 JSONL 行；追加一条完整的新记录，并用 `--supersedes "<旧 event_id>"` 指向前序事件。`approve` 仅在参赛队真实确认后执行。代码模式在 G2 前先运行一次 `replay`，冻结后再运行一次；交互模式由队员在独立副本实际操作，并在 G2 前、冻结后各运行一次 `record-manual-replay`，把执行人、操作说明和逐项文件哈希绑定当前 run/freeze。洁净副本只复制全部代码和 `declared_inputs`，从空结果目录生成与当前项目输出逐项一致的声明输出。赛题官方附件另列入 `official_attachment_inputs`：参与重放，但不强制重复进入支撑包；自主查阅且实际使用的数据以结构化 `data_inventory` 登记，并强制进入支撑包。引擎以 `shell=False` 调用受信运行器，但 Windows 仍可能按系统规则处理项目内批处理文件；这不是操作系统进程安全沙箱，只能运行队伍信任的命令。完整命令、状态变更和精确字段见 [references/architecture.md](references/architecture.md) 与 [references/artifact-schemas.md](references/artifact-schemas.md)。

## 选题与建模策略

选题和模型设计阶段读取 [references/problem-playbooks.md](references/problem-playbooks.md)。执行以下原则：

1. 先建立题目包和问题 DAG，再选算法；不得以算法名称替代问题分析。
2. 每问至少保留一个可解释 baseline、一个主方案和一个失败时可退回的 fallback。这里要求的是功能角色，不强迫三个复杂模型。
3. 创新来自机制、约束、数据使用、验证或决策价值，不来自无意义堆叠算法。
4. 跨问题传递的不只是点估计，还包括误差、假设和适用范围。
5. 对陌生题型先做守恒、量纲、边界、可识别性和最小可行模型分析，再查找方法。

现有资源按需使用：

- 算法索引：`../math-modeling/assets/README.md`
- CUMCM 优秀论文说明：`../math-modeling/references/Outstanding Thesis/README.md`
- CUMCM 历年论文：`../math-modeling/references/Outstanding Thesis/CUMCM/`
- Word/PDF/Excel 处理：使用已安装的 `docx`、`pdf`、`xlsx` 技能，遵守各自渲染与复核流程。

优秀论文只用于学习论证结构、模型深度和图表表达，不得复制文字、模型组合或结果。

## 结果冻结与论文约束

- 每个论文数字都必须能回到 `result_ledger.json` 的条目及产生它的脚本/数据。
- `work/results` 与 `work/figures` 的全部非临时文件必须列入 `expected_outputs` 并由重放重新生成；旧图、缓存和未声明中间结果不得进入结论证据。
- 冻结前必须完成独立复算、量纲、边界、异常值、敏感性或稳健性检查；不能用“代码成功运行”代替验证。
- 冻结后绘图和排版只能改变呈现，不得静默改变数值、样本、参数或统计口径。
- 每条关键结论必须在 `claim_evidence.json` 中映射到结果、图表、代码或文献；没有证据的结论删除或降级措辞。
- 公式、表格和图每次修改后即时检查，终稿再按最终渲染件逐项复核。

## Nature 能力的受控接入

需要文献核验、科研绘图或特定语言处理时读取 [references/nature-routing.md](references/nature-routing.md)。总原则：借用证据检索、图形 QA 和审稿式质疑，不照搬 Nature 的期刊叙事、CNS 引文范围或英文风格。

## 三席审计

复核阶段读取 [references/review-rubric.md](references/review-rubric.md)，独立完成：

- 建模席：题意覆盖、假设、公式、模型深度、不确定性和决策有效性。
- 复现席：适用时检查环境、入口、路径、数据、随机性、结果账本和论文数字一致性；`program_usage=none` 时改查解析推导、人工复算和附录声明。
- 评阅席：摘要信息密度、论证可读性、图表证据、引用、匿名与当届格式。

三席不得共享“预期答案”。先各自列证据与阻断项，再合并去重。任何事实冲突都回到代码与账本处理，不能靠润色掩盖。

## 审计边界

- 门禁批准是队伍自证，不是现实身份认证；哈希清单、事件链和重放报告自哈希用于发现漂移，不是不可抵赖数字签名。
- 自动重放隔离项目文件集合，不隔离网络、系统文件、用户目录或安装环境；只执行队伍信任的入口与运行器。
- 交互重放报告是结构化、哈希绑定的队伍自证；引擎不自动操作 Excel/SPSS 等软件，也不证明许可证或外部运行环境可用。
- `official_attachment_inputs.source_ref`、RAR/超安全上限 ZIP、PDF 页数/版式、图片水印和未知身份词仍需团队人工核验。
- 引擎能阻止不完整、不一致和不可复现的交付，不能替代数学正确性判断，也不承诺奖项。

## 完成条件

只有同时满足以下条件才可称为完成：

- G0–G4 均有真实团队批准，且各批准绑定的证据摘要仍有效；
- `audit --stage delivery` 无 `BLOCKER`；
- 使用 `code/interactive`、自主使用数据或当届要求提交支撑材料时，支撑材料可重放且关键输出与冻结账本一致；`program_usage=none` 且确无自主数据、必要中间材料或 AI 明细、`support_required=false` 时，以解析复核、结构化来源账本、`no_support_reason` 和论文附录声明替代；
- 论文及所有提交文件通过匿名、页数、大小、附件和引用检查；
- AI 声明与实际日志一致；使用 AI 时 `support_required=true`，且规定明细 PDF 已实际进入清单一致的支撑归档（允许位于归档子目录）；
- `lock` 成功生成 `reports/final_lock.json`，完整证据包受哈希锁定，锁后不再变化。

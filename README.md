# CUMCM 国赛论文交付 Skill

这是一套面向全国大学生数学建模竞赛（CUMCM、高教社杯）的中文总控 Skill。它把赛题、附件与原始数据推进为可快速阅卷、可复算、可追溯的正式论文和支撑材料，也可用于审查、修订已有竞赛论文。

## 主要能力

- 核验竞赛规则、模板、匿名要求和 AI 使用边界。
- 拆解赛题，建立问题依赖图、数据合同与模型合同。
- 组织数据审计、基线模型、主模型、回退模型和工程验证。
- 统一代码、公式、正文数值、图表与支撑材料的结果口径。
- 生成以快速阅卷为导向的中文竞赛论文，控制术语密度和结论边界。
- 制作准确、鲜明且可打印的科研图，默认白底表格、无跨列合并。
- 完成多角色终审、公式复核、DOCX/PDF 渲染检查与交付审计。

## 安装

将本仓库克隆或下载到 Codex 的个人 Skills 目录，并确保最终目录名为 `cumcm-paper-delivery`：

```text
~/.codex/skills/cumcm-paper-delivery/
├── SKILL.md
├── agents/
├── references/
└── scripts/
```

重新启动 Codex 或刷新 Skills 后即可使用。

## 使用方式

可以直接在任务中写：

```text
请使用 $cumcm-paper-delivery，从赛题和附件开始完成 CUMCM 建模、求解、论文、图表、复核和最终交付。
```

也可以指定工作模式：

- 从零建模：从规则核验、题目拆解和数据审计开始。
- 修改已有论文：先冻结公式、数值与模板基线，再进行定向修改。
- 终审评分：只复核和报告，不在未授权时改写正文或重跑实验。

## 依赖检查

本 Skill 会按阶段调用其他本地 Skills。运行下面的脚本可检查依赖是否齐全：

```powershell
python scripts/check_dependencies.py
```

依赖分为“必需、推荐、条件启用”三类，完整说明见 `references/dependency-map.md` 和 `references/dependency-manifest.json`。

## 设计原则

- 创新来自机制、约束、数据利用、不确定性和工程闭环，不靠堆叠算法名词。
- 每项核心结论必须能回溯到数据、代码、公式、图表、验证或文献。
- 数值图必须由准确数据生成，不用无法复算的 AI 截图冒充实验结果。
- 正文不暴露 Agent 推理、内部审稿规则或制作流程。
- 优先保证竞赛快速阅卷体验，同时保留必要的技术严谨性。

## 目录说明

- `SKILL.md`：总控流程与触发说明。
- `agents/openai.yaml`：Codex 界面元数据。
- `references/from-zero-workflow.md`：从零建模全流程。
- `references/quality-gates.md`：交付质量门槛。
- `references/review-and-scoring.md`：多角色审稿与评分框架。
- `references/figure-style.md`：图表与版式规范。
- `references/dependency-map.md`：依赖关系与调用策略。
- `scripts/check_dependencies.py`：本地依赖检查脚本。

## 使用提醒

本 Skill 不承诺奖项结果，也不能替代参赛队对官方规则、数据来源、模型假设和最终提交内容的责任。比赛期间应以当届官方文件为准，并如实遵守 AI 工具使用与披露要求。


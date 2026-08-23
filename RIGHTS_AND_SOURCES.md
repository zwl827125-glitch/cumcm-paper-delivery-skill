# 权利、来源与再分发说明

## 1. 仓库原创集成内容

根目录的总控 Skill、安装器、依赖检查器、本地 Office 桥及本仓库新增的公开发行说明按 Apache License 2.0 提供，除非文件或所在目录另有声明。

仓库维护者确认：多项琐碎资料由同学协作整理，同学已明确委托并允许与本 Skill 一起公开发布。该授权覆盖整理包的公开再分发，但不把第三方论文或软件的著作权转移给维护者。

## 2. CUMCM 论文资源

论文著作权归原作者或相关权利人，不适用仓库根目录的 Apache‑2.0 许可证。

- 12 篇 2022–2024 正文精选来自中国大学生在线官方展示页，逐篇链接见 `dependencies/math-modeling/references/Outstanding Thesis/README.md`。
- 11 篇历史精选可追溯到 `ZSLlearn/my-math-modeling-skill` 的历史提交 `bffe04f88ef646dc9db8781e8555ccb5a486c9bc`，并依据整理者向仓库维护者提供的公开再分发授权随包发布。
- 资源只用于学习结构、模型路线、验证和图表逻辑。使用者不得冒充作者，不得照抄论文文字、图表或结论。
- 如权利人认为文件应移除，可通过仓库 Issue 提供文件路径和权利依据，维护者应及时复核处理。

## 3. Nature Skills

`dependencies/nature-figure`、`dependencies/nature-academic-search` 和 `dependencies/nature-shared` 来自：

<https://github.com/Yuan1z0825/nature-skills>

选取版本：`a6e6f3456f2065eb555afe8ed2c28637f3cd4e1b`。

上游按 Apache License 2.0 发布；许可证副本保存在各依赖目录中。

`figures4papers` 的第三方脚本和预览图没有打包，因为审计时其上游没有明确的根目录再分发许可证。本包只保留外部链接和原创复刻边界：

<https://github.com/ChenLiu-1996/figures4papers>

## 4. 数学建模与绘图 Skill

- 数学建模资源来源与演化线索：<https://github.com/XiaoMaColtAI/math-modeling-skill>
- 竞赛科研绘图 Skill：<https://github.com/zwl827125-glitch/modeling-research-figure-skill>

`modeling-research-figure-skill` 保留其 Apache‑2.0 `LICENSE` 和 `NOTICE.md`。

## 5. 未再分发的专有工具

以下本地旧工具的 `SKILL.md` 仍标为 `license: Proprietary`，因此未复制：

- `math-modeling/tools/docx`
- `math-modeling/tools/pdf`
- `math-modeling/tools/xlsx`

公开包没有从这些目录复制提示词、代码、脚本、资产或许可证文本。等价能力由新写的 `scripts/office_bridge.ps1`、`scripts/build_paper.ps1` 和开源 Python/Pandoc 依赖提供。

## 6. 商标与竞赛组织

CUMCM、高教社杯、Nature、OpenAI、Anthropic、Microsoft 等名称仅用于说明兼容范围、来源或运行后端。仓库与这些组织无隶属或背书关系。

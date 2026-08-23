# 技能依赖与公开发行边界

## 仓库内置技能

| 阶段 | 技能 | 主要能力 |
|---|---|---|
| 全程总控 | `cumcm-competition-engine` | CUMCM 规则、阶段合同、结果冻结、复核和交付审计 |
| 算法底座 | `math-modeling` | CUMCM 算法索引、角色路由与 23 篇国赛论文资源 |
| 题目分析 | `cumcm-modeler`（建模手） | 问题 DAG、假设、变量、模型合同与创新设计 |
| 代码复算 | `cumcm-solver`（编程手） | 数据审计、求解代码、独立复算、结果冻结与可视化 |
| 中文论文 | `cumcm-writer`（论文手） | 国赛论文结构、快速阅卷表达、公式和版式检查 |
| 文献检索 | `paper-search` | OpenAlex 与检索服务交叉验证建模文献 |
| 竞赛绘图 | `modeling-research-figure-skill` | CUMCM 数据图、流程图、证据图和视觉 QA |
| 高阶绘图 | `nature-figure` + `nature-shared` | 多面板证据架构、Python/R 绘图、出版级导出和 QA |
| 深度文献 | `nature-academic-search` | 多数据库检索、引文核对、去重和引用文件管理 |

## 可互换的文件后端

本公开包不绑定 Codex。运行时按当前环境选择一条可用路线：

| 文件类型 | 依赖 | 用途 |
|---|---|---|
| Word | 本地 Word COM；或 `documents:documents`；或 Pandoc/Python | 创建、修改、更新域、统计公式、渲染和逐页核查 DOCX |
| PDF | Python PDF 库；或 `pdf:pdf`；或 LibreOffice/Poppler | 读取、OCR、渲染和核查赛题、规定、模板及参考论文 |
| 表格 | 本地 Excel COM；或 `spreadsheets:Spreadsheets`；或 openpyxl/pandas | 清洗、审计和生成 XLSX/CSV，强制重算公式 |

Windows 本地 Office 入口为 `scripts/office_bridge.ps1`；Markdown 到 DOCX 的入口为 `scripts/build_paper.ps1`。Codex 插件只是可选加速器，不是安装前提。

## 未再分发内容

- `math-modeling/tools/docx`
- `math-modeling/tools/pdf`
- `math-modeling/tools/xlsx`

上述三个旧工具目录的许可证明确禁止复制和向第三方分发。公开版仅替换调用入口，不复制其代码、提示词、脚本或资产。

`nature-figure/assets/figures4papers` 也不随包发布，因为上游未提供明确的再分发许可证。公开版保留来源链接和原创复刻原则，不保留其脚本与预览图。

## 默认路由

1. `cumcm-paper-delivery` 接收用户任务并区分赛题、模板与用户指令。
2. `cumcm-competition-engine` 决定阶段、规则和交付门禁。
3. 建模、求解、写作分别加载 `cumcm-modeler`、`cumcm-solver`、`cumcm-writer`。
4. 竞赛图优先使用 `modeling-research-figure-skill`；需要多面板期刊级证据架构时调用 `nature-figure`。
5. 文档、PDF 和表格文件调用 Codex 插件能力。
6. 全程以真实数据、可运行代码、结果账本和最终渲染稿为证据源。

依赖清单的机器可读版本见 [dependency-manifest.json](dependency-manifest.json)。

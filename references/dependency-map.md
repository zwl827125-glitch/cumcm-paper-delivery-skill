# 技能依赖与调用记录

## E4 项目实际调用

本次“确定山体海拔高度”论文的最终生产与修订阶段实际读取或调用了以下技能：

| 作用 | 技能 | 使用内容 |
|---|---|---|
| 国赛总控 | `cumcm-competition-engine` | CUMCM 任务边界、论文与支撑材料合同、合规和终审 |
| 代码与复算 | `编程手` | 求解入口、结果冻结、数值复算、可重复性 |
| 中文论文 | `论文手` | 竞赛论文结构、摘要、正文和快速阅卷表达 |
| 科研绘图 | `nature-figure` | Python 图形设计、导出和图件 QA |
| Word 处理 | `docx` | DOCX、Office Math、图表和格式修改 |
| 文档终检 | `documents:documents` | 渲染后检查 Word 页面布局 |
| PDF 操作 | `pdf` | PDF 导出与基础检查 |
| PDF 终检 | `pdf:pdf` | Poppler 渲染、逐页视觉 QA |

最终版本没有使用 `imagegen` 生成数值截图，也没有使用 `nature-writing`、`nature-polishing` 或期刊投稿类技能改写论文。

## 从零建模新增依赖

| 阶段 | 技能 | 新增能力 |
|---|---|---|
| 全程总控 | `math-modeling` | 算法索引、优秀论文库以及文档工具资源，不接管国赛规则 |
| 题目分析 | `建模手` | 问题 DAG、模型合同、假设、变量、算法和术语 |
| 数据入口 | `xlsx` | 读取、清洗、审计 Excel/CSV/TSV 数据及公式错误 |
| 复杂工作簿 | `spreadsheets:Spreadsheets` | 多表结构分析、工作簿级检查和图表输出，按需使用 |
| 文献入口 | `paper-search` | OpenAlex 与 AnySearch 交叉验证式建模文献检索 |
| 深度文献 | `nature-academic-search` | 多数据库检索、引文核对、去重与引用文件管理，按需使用 |
| 原始题目 | `pdf`、`pdf:pdf`、`docx` | 读取赛题、附件、模板并完成视觉核验 |
| 多角色终审 | `cumcm-competition-engine` 内置三席 + 本 Skill 复核合同 | 建模、复现、评阅和恶意攻击式问题闭环 |

## 明确不纳入运行主链

- `nature-writing`、`nature-polishing`：期刊叙事和英文风格可能覆盖国赛中文结构。
- `nature-citation`：严格 CNS 引文范围不适合作为国赛通用参考文献入口。
- `nature-reviewer`：Nature 审稿标准不等于 CUMCM 评分标准。
- `imagegen`：不用于生成无法复算的数值图；概念插图只有用户明确要求时才单独使用。
- `presentations:Presentations`、`nature-paper2ppt`：路演/PPT 不属于电子论文主链。

“加入”指将这些技能写入总控路由和依赖清单。运行时仍按阶段最小加载，避免上下文拥挤或规范冲突。


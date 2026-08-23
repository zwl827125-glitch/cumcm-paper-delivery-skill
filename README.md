# CUMCM 从零建模与论文交付 Skill 完整发行版

面向全国大学生数学建模竞赛（CUMCM、高教社杯）的中文全流程 Skill：从读题、数据审计、创新模型、代码复算、图证设计到 Word 论文、支撑材料、AI 合规和终审评分。

本仓库采用“创新优先、图证优先、证据可追溯”的竞赛快速阅卷策略，同时保留公式、数值、代码和工程验证的复算链。

## 这次公开了什么

| 组件 | 作用 | 是否内置 |
|---|---|---:|
| `cumcm-paper-delivery` | 从零建模与中文论文交付总控 | 是 |
| `cumcm-competition-engine` | 国赛规则、阶段合同、结果冻结和终审 | 是 |
| `math-modeling` | CUMCM 算法库、角色路由和国赛论文资源 | 是 |
| `cumcm-modeler` / `cumcm-solver` / `cumcm-writer` | 建模手、编程手、论文手三个专业角色 | 是 |
| `paper-search` | OpenAlex 等建模文献检索 | 是 |
| `modeling-research-figure-skill` | 数模竞赛绘图、重画和视觉 QA | 是 |
| `nature-figure` / `nature-shared` | 多面板证据架构和期刊级科研绘图 | 是 |
| `nature-academic-search` | 多源文献检索与引文核对 | 是 |
| CUMCM 优秀论文 | 23 篇，只含国赛，不含 64 篇 MCM/ICM | 是 |
| 本地 Office 桥 | 直接调用 Windows Word/Excel | 是 |

原来 1.2 GB 的大包主要包含训练项目、重复数据、缓存、字体、压缩包和第三方目录。本仓库只发布建模交付真正需要的可分发组件，因此体积明显更小，但主流程更完整。

## 不要求必须使用 Codex

任何能够读取 `SKILL.md`、访问文件和执行命令的 Agent 都可以使用本仓库。推荐顺序：

1. 让 Agent 读取根目录 `SKILL.md`。
2. 按阶段读取 `dependencies/` 中对应 Skill。
3. Windows 用户可直接调用本地 Microsoft Word 和 Excel。
4. 无 Office 环境可使用 Pandoc、LibreOffice 和 `requirements.txt` 中的 Python 库。

Codex 的文档、PDF、表格插件是可选加速器，不是运行前提。

## Windows 本地 Office

检查 Word、Excel、Pandoc 和 LibreOffice：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\office_bridge.ps1 -Action probe
```

检查 Word 页数、公式、表格和图片数量：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\office_bridge.ps1 `
  -Action inspect-word -InputPath .\论文.docx
```

更新域、目录和分页：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\office_bridge.ps1 `
  -Action refresh-word -InputPath .\论文.docx
```

生成仅供视觉 QA 的 PDF：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\office_bridge.ps1 `
  -Action word-to-pdf -InputPath .\论文.docx -OutputPath .\qa\论文预览.pdf
```

强制重算 Excel：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\office_bridge.ps1 `
  -Action excel-recalc -InputPath .\支撑材料\结果.xlsx
```

脚本通过 COM 调用用户本机安装的 Office，打开文档时强制禁用宏自动执行。

## Markdown 生成 DOCX

安装 Pandoc 后，可用参考模板生成 DOCX，并自动交给本地 Word 更新：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_paper.ps1 `
  -SourceMarkdown .\paper.md `
  -OutputDocx .\论文.docx `
  -ReferenceDocx .\dependencies\cumcm-writer\references\论文模板.docx
```

Python 环境：

```bash
python -m pip install -r requirements.txt
python scripts/check_dependencies.py
python scripts/verify_release.py
```

## 安装到 Agent 的 Skills 目录

Codex 默认安装：

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

安装到任意兼容 Agent 的 Skills 目录：

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1 -TargetRoot "D:\agent\skills"
```

跨平台：

```bash
python install.py --target /path/to/agent/skills
```

安装器只复制本仓库明确列出的 Skill，不删除目标目录里的其他内容。更新已有版本时显式加 `-Force` 或 `--force`。

## 23 篇国赛论文

位置：

`dependencies/math-modeling/references/Outstanding Thesis/CUMCM/`

- 历史精选：11 篇
- 2022–2024 中国大学生在线官方正文精选：12 篇
- MCM/ICM：0 篇

索引、官方页面和使用边界见：

`dependencies/math-modeling/references/Outstanding Thesis/README.md`

SHA‑256 见 `PAPER_CHECKSUMS.sha256`。

## 授权边界

仓库原创集成代码默认按 Apache‑2.0 发布，但第三方组件和论文保留各自权利与来源。23 篇论文的整理与公开再分发由仓库维护者确认已获同学整理者授权；论文著作权仍归原作者或相关权利人。

以下原始第三方目录没有复制进仓库：

- `math-modeling/tools/docx`
- `math-modeling/tools/pdf`
- `math-modeling/tools/xlsx`
- `nature-figure/assets/figures4papers` 的第三方脚本与预览图

前三者仍标记为 Proprietary；删除本地许可证文件不会改变其授权属性。公开版使用本仓库自研 Office 桥和开源库路线补齐能力。

完整来源和权利说明见 [RIGHTS_AND_SOURCES.md](RIGHTS_AND_SOURCES.md)。

## 免责声明

本项目不隶属于全国大学生数学建模竞赛组委会、中国大学生在线、Nature Portfolio、OpenAI 或 Anthropic。竞赛期间必须核对当届官方规则和 AI 使用规定；往届论文与模板不构成当届规则。

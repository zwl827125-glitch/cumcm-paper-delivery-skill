#!/usr/bin/env python3
"""Build the self-contained offline HTML gallery from the JSON catalogs."""

from __future__ import annotations

import html
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CATALOG = json.loads((ROOT / "references" / "catalog.json").read_text(encoding="utf-8"))
REFERENCES = json.loads((ROOT / "references" / "reference-assets.json").read_text(encoding="utf-8"))

STATUS_LABELS = {
    "runnable": "可运行模板",
    "static-reference": "静态参考",
    "source-reference": "来源参考",
    "qa-only": "QA 对比",
}


def card(item: dict, *, auxiliary: bool = False) -> str:
    title = item.get("title_zh") or item["id"]
    title_en = item.get("title_en", "")
    preview = item.get("preview") or item["path"]
    status = item.get("status", "reference")
    status_label = STATUS_LABELS.get(status, status)
    collection = item.get("collection", status)
    tags = item.get("tags", item.get("content", []))
    vector = item.get("vector")
    generator = item.get("generator")
    links = [f'<a href="{html.escape(preview)}">PNG</a>']
    if vector:
        links.append(f'<a href="{html.escape(vector)}">SVG</a>')
    if generator:
        links.append(f'<a href="{html.escape(generator)}">代码</a>')
    searchable = " ".join(
        [item.get("id", ""), title, title_en, collection, status, *tags]
    ).casefold()
    tag_markup = "".join(f"<span>{html.escape(str(tag))}</span>" for tag in tags[:6])
    auxiliary_class = " auxiliary" if auxiliary else ""
    return f'''<article class="card{auxiliary_class}" data-search="{html.escape(searchable)}" data-collection="{html.escape(collection)}" data-status="{html.escape(status)}">
      <a class="image-link" href="{html.escape(preview)}"><img src="{html.escape(preview)}" alt="{html.escape(title)}"></a>
      <div class="body">
        <div class="meta"><b>{html.escape(status_label)}</b><code>{html.escape(item['id'])}</code></div>
        <h3>{html.escape(title)}</h3>
        <p>{html.escape(title_en)}</p>
        <div class="tags">{tag_markup}</div>
        <div class="links">{' · '.join(links)}</div>
      </div>
    </article>'''


formal_cards = "\n".join(card(item) for item in CATALOG["items"])
source_cards = "\n".join(card(item, auxiliary=True) for item in REFERENCES["items"] if item["status"] == "source-reference")
qa_cards = "\n".join(card(item, auxiliary=True) for item in REFERENCES["items"] if item["status"] == "qa-only")

document = f'''<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>数模与科研绘图图库</title>
  <style>
    :root {{ --ink:#17212b; --muted:#62707c; --line:#dfe6eb; --paper:#fff; --wash:#f3f6f8; --blue:#165a9f; --green:#18794e; --amber:#946200; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; color:var(--ink); background:var(--wash); font-family:Inter,"Microsoft YaHei","PingFang SC",Arial,sans-serif; line-height:1.55; }}
    main {{ width:min(1500px,calc(100% - 36px)); margin:auto; padding:42px 0 72px; }}
    header,section,details {{ background:var(--paper); border:1px solid var(--line); border-radius:18px; }}
    header {{ padding:34px 38px; }}
    section,details {{ margin-top:22px; padding:28px; }}
    h1 {{ margin:0 0 10px; font-size:clamp(30px,4vw,52px); line-height:1.12; }}
    h2 {{ margin:0 0 14px; }}
    p {{ color:var(--muted); }}
    .stats {{ display:flex; flex-wrap:wrap; gap:10px; margin-top:20px; }}
    .stat {{ padding:9px 13px; background:#edf4fa; border-radius:999px; font-weight:700; color:#24465f; }}
    .controls {{ display:grid; grid-template-columns:2fr 1fr 1fr; gap:10px; margin:18px 0 22px; }}
    input,select {{ width:100%; padding:11px 12px; border:1px solid #cfd8de; border-radius:10px; background:white; color:var(--ink); font:inherit; }}
    .grid {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:16px; }}
    .card {{ border:1px solid var(--line); border-radius:14px; overflow:hidden; background:white; align-self:start; }}
    .card[hidden] {{ display:none; }}
    .image-link {{ display:block; background:white; }}
    .card img {{ display:block; width:100%; height:310px; object-fit:contain; }}
    .card.auxiliary img {{ height:260px; }}
    .body {{ padding:14px 15px 16px; border-top:1px solid var(--line); }}
    .meta {{ display:flex; justify-content:space-between; gap:10px; align-items:center; font-size:12px; color:var(--muted); }}
    .meta b {{ color:var(--green); background:#e6f5ed; border-radius:999px; padding:3px 8px; }}
    .meta code {{ overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
    h3 {{ margin:10px 0 3px; font-size:17px; }}
    .body p {{ margin:0 0 9px; font-size:13px; }}
    .tags {{ display:flex; flex-wrap:wrap; gap:6px; }}
    .tags span {{ padding:3px 7px; border-radius:999px; background:#eef2f4; color:#53616d; font-size:11px; }}
    .links {{ margin-top:11px; font-size:13px; }}
    a {{ color:var(--blue); text-decoration:none; font-weight:650; }}
    summary {{ cursor:pointer; font-size:20px; font-weight:750; }}
    .notice {{ border-left:4px solid #d99a27; background:#fff8e8; padding:12px 14px; color:#624b16; border-radius:8px; }}
    footer {{ color:var(--muted); text-align:center; padding:24px 0 0; font-size:13px; }}
    @media(max-width:1050px) {{ .grid {{ grid-template-columns:repeat(2,minmax(0,1fr)); }} }}
    @media(max-width:700px) {{ main {{ width:min(100% - 18px,1500px); padding-top:12px; }} header,section,details {{ padding:20px; }} .controls,.grid {{ grid-template-columns:1fr; }} .card img {{ height:auto; }} }}
  </style>
</head>
<body>
<main>
  <header>
    <h1>数模与科研绘图图库</h1>
    <p>用于 CUMCM、MCM/ICM 和科研论文的静态参考、视觉复现与图片润色。复用视觉语法，不从像素猜测隐藏数据。</p>
    <div class="stats">
      <span class="stat">35 张正式图库图</span>
      <span class="stat">16 个可运行模板</span>
      <span class="stat">20 个 SVG</span>
      <span class="stat">55 张唯一 PNG 资产</span>
      <span class="stat">40+ 图型与构图模式</span>
    </div>
  </header>

  <section>
    <h2>正式图库</h2>
    <p class="notice">静态参考同样可以用于高保真视觉重建；只有标记为“可运行模板”的条目附带现成 Python 生成器。任何科研数值都必须来自真实分析。</p>
    <div class="controls">
      <input id="query" type="search" placeholder="搜索：optimization、sensitivity、热图、imaging…">
      <select id="collection"><option value="">全部集合</option><option value="modeling-template">可运行数模模板</option><option value="modeling-example">数模静态示例</option><option value="chart-atlas">科研图型图谱</option><option value="multi-panel-blueprint">科研多面板蓝图</option></select>
      <select id="status"><option value="">全部状态</option><option value="runnable">可运行模板</option><option value="static-reference">静态参考</option></select>
    </div>
    <div id="formal-grid" class="grid">
{formal_cards}
    </div>
  </section>

  <details>
    <summary>11 张原始参考截图</summary>
    <p>这些是经发布者明确授权随 Skill 公开的重建参考，不属于 35 张正式模板。</p>
    <div class="grid">{source_cards}</div>
  </details>

  <details>
    <summary>9 张原图—复刻图 QA 对比板</summary>
    <p>用于检查布局、几何、标注和可见关系，不属于可直接替换数据的模板。</p>
    <div class="grid">{qa_cards}</div>
  </details>

  <footer>开源 Codex Skill · Apache-2.0 · 与期刊出版方及竞赛组织方无隶属关系</footer>
</main>
<script>
  const query = document.getElementById('query');
  const collection = document.getElementById('collection');
  const status = document.getElementById('status');
  const cards = [...document.querySelectorAll('#formal-grid .card')];
  function applyFilters() {{
    const q = query.value.trim().toLowerCase();
    for (const card of cards) {{
      const textMatch = !q || card.dataset.search.includes(q);
      const collectionMatch = !collection.value || card.dataset.collection === collection.value;
      const statusMatch = !status.value || card.dataset.status === status.value;
      card.hidden = !(textMatch && collectionMatch && statusMatch);
    }}
  }}
  query.addEventListener('input', applyFilters);
  collection.addEventListener('change', applyFilters);
  status.addEventListener('change', applyFilters);
</script>
</body>
</html>
'''

(ROOT / "index.html").write_text(document, encoding="utf-8", newline="\n")
print(f"Wrote {ROOT / 'index.html'} with {len(CATALOG['items'])} formal cards and {len(REFERENCES['items'])} auxiliary cards.")

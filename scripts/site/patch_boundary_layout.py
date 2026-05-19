#!/usr/bin/env python3
"""Replace system boundary tables with two-column bullet lists in data.js."""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DATA_JS = REPO / "data.js"

AVOID = [
    "短期暴利",
    "精准抄底逃顶",
    "追逐热门赛道",
    "依赖消息和大 V",
    "高频交易",
    "杠杆放大收益",
    "预测宏观短期变化",
]
PURSUE = [
    "长期正复利",
    "低估买入",
    "现金流可见",
    "分红复投",
    "分散容错",
    "周期轮动",
    "股权传承",
    "心性稳定",
]


def col(title: str, items: list[str]) -> str:
    lis = "".join(f"<li>{html.escape(it)}</li>" for it in items)
    return (
        f'<div class="system-boundary-col">'
        f'<h3 class="system-boundary-heading">{html.escape(title)}</h3>'
        f'<ul class="system-boundary-list">{lis}</ul>'
        f"</div>"
    )


def boundary_html(avoid: list[str], pursue: list[str]) -> str:
    grid = f'<div class="system-boundary-grid">{col("不追求", avoid)}{col("追求", pursue)}</div>'
    return f'<h2 id="体系边界">体系边界</h2>\n{grid}\n'


def extract_from_tables(text: str) -> tuple[list[str], list[str]] | None:
    tables = re.findall(r'<table class="system-table"[\s\S]*?</table>', text)
    if len(tables) < 2:
        return None
    items: list[list[str]] = []
    for tbl in tables[:2]:
        rows = re.findall(r"<td>([\s\S]*?)</td>", tbl)
        items.append([re.sub(r"[；;]\s*$", "", r.strip()) for r in rows])
    return items[0], items[1]


def main() -> None:
    raw = DATA_JS.read_text(encoding="utf-8")
    data = json.loads(raw.removeprefix("window.SHENGSHI_DATA = ").strip().rstrip(";"))
    boundary = data.get("systemSections", {}).get("boundary", "")
    parsed = extract_from_tables(boundary)
    avoid, pursue = parsed if parsed else (AVOID, PURSUE)
    new_boundary = boundary_html(avoid, pursue)
    data.setdefault("systemSections", {})["boundary"] = new_boundary

    if "systemHtml" in data and "体系边界" in data["systemHtml"]:
        data["systemHtml"] = re.sub(
            r'<h2[^>]*>体系边界</h2>[\s\S]*?(?=<h2|$)',
            new_boundary,
            data["systemHtml"],
            count=1,
        )

    body = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    DATA_JS.write_text(f"window.SHENGSHI_DATA = {body};\n", encoding="utf-8")
    print(f"patched boundary: {len(avoid)} avoid, {len(pursue)} pursue")


if __name__ == "__main__":
    main()

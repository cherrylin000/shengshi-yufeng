#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Merge broken <ol><li>…</li><p>…</p></ol> sequences into one numbered list."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_JS = ROOT / "data.js"
ALL_HTML = ROOT / "all.html"

def merge_broken_ols(html: str) -> str:
    """Only merge the four asset-type items under 偏好以下资产."""
    inner = re.compile(
        r"(<p>体系明显偏好以下资产：</p>\s*)"
        r"(?:<ol>\s*<li>[\s\S]*?</li>\s*<p>[\s\S]*?</p>\s*</ol>\s*){4}",
        re.I,
    )
    outer = re.compile(
        r"(<p>体系明显偏好以下资产：</p>\s*)"
        r"(?:<ol>\s*<li>[\s\S]*?</li>\s*</ol>\s*<p>[\s\S]*?</p>\s*){4}",
        re.I,
    )
    block = """<ol class="system-enum-list">
<li><strong>核心央企、国企、大型金融机构</strong><p>例如大行、保险、再保险、不良资产处置机构等。逻辑是国家信用、行业地位、规模优势、长期存在概率较高。</p></li>
<li><strong>国计民生行业</strong><p>能源、石化、电信、电力、水电、交通基础设施、铁路、高速、港口、机场等。这些行业变化慢、需求长期存在、现金流较稳定。</p></li>
<li><strong>成熟高分红行业</strong><p>增速未必高，但利润真实，分红稳定，估值低，能给小股东现金回报。</p></li>
<li><strong>低估的硬资产和现金流资产</strong><p>资产真实、行业长寿、价格低于保守价值。</p></li>
</ol>
"""
    if inner.search(html):
        return inner.sub(r"\1" + block, html, count=1)
    if outer.search(html):
        return outer.sub(r"\1" + block, html, count=1)
    return html


def patch_data_js() -> None:
    raw = DATA_JS.read_text(encoding="utf-8")
    prefix = "window.SHENGSHI_DATA = "
    data = json.loads(raw.removeprefix(prefix).strip().rstrip(";"))
    before = data["systemHtml"]
    after = merge_broken_ols(before)
    if before == after:
        print("data.js: no broken ol runs found")
        return
    data["systemHtml"] = after
    body = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    DATA_JS.write_text(f"{prefix}{body};\n", encoding="utf-8")
    print("data.js: patched systemHtml")


def patch_all_html() -> None:
    text = ALL_HTML.read_text(encoding="utf-8")
    after = merge_broken_ols(text)
    if text == after:
        print("all.html: no broken ol runs found")
        return
    ALL_HTML.write_text(after, encoding="utf-8")
    print("all.html: patched")


if __name__ == "__main__":
    patch_data_js()
    patch_all_html()

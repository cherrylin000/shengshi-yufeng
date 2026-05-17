#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Restore systemHtml from git, then merge only asset-type broken lists."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_JS = ROOT / "data.js"
ALL_HTML = ROOT / "all.html"
REPO = ROOT.parent

ASSET_BLOCK = """<ol class="system-enum-list">
<li><strong>核心央企、国企、大型金融机构</strong><p>例如大行、保险、再保险、不良资产处置机构等。逻辑是国家信用、行业地位、规模优势、长期存在概率较高。</p></li>
<li><strong>国计民生行业</strong><p>能源、石化、电信、电力、水电、交通基础设施、铁路、高速、港口、机场等。这些行业变化慢、需求长期存在、现金流较稳定。</p></li>
<li><strong>成熟高分红行业</strong><p>增速未必高，但利润真实，分红稳定，估值低，能给小股东现金回报。</p></li>
<li><strong>低估的硬资产和现金流资产</strong><p>资产真实、行业长寿、价格低于保守价值。</p></li>
</ol>"""

SYSTEM_QUESTIONS = """<ol class="system-enum-list system-enum-list--plain">
<li>买什么；</li>
<li>为什么买；</li>
<li>什么时候买；</li>
<li>买多少；</li>
<li>怎么持有；</li>
<li>什么时候轮动或卖出；</li>
<li>出错怎么办。</li>
</ol>"""

ENUM_CSS = """
.system ol.system-enum-list{list-style:none;counter-reset:system-enum;padding:0;margin:16px 0}
.system ol.system-enum-list>li{counter-increment:system-enum;position:relative;padding-left:2.6em;margin:14px 0}
.system ol.system-enum-list>li::before{content:"（" counter(system-enum) "）";position:absolute;left:0;font-family:var(--mono);font-size:13px;color:var(--accent);font-weight:500}
.system ol.system-enum-list>li>p{margin:8px 0 0;color:#3a382f;line-height:1.55}
.system ol.system-enum-list>li>strong{font-weight:500}
.system ol.system-enum-list--plain>li::before{font-weight:500}
"""


def git_system_html() -> str:
    raw = subprocess.check_output(
        ["git", "-C", str(REPO), "show", "7e0a07f:shengshi-yufeng/data.js"],
        text=True,
        encoding="utf-8",
    )
    data = json.loads(raw.split("=", 1)[1].strip().rstrip(";"))
    return data["systemHtml"]


def fix_asset_section(html: str) -> str:
    # data.js: ol-li-p inside ol (invalid)
    inner = re.compile(
        r"(<p>体系明显偏好以下资产：</p>\s*)"
        r"(?:<ol>\s*<li>[\s\S]*?</li>\s*<p>[\s\S]*?</p>\s*</ol>\s*){4}",
        re.I,
    )
    if inner.search(html):
        return inner.sub(r"\1" + ASSET_BLOCK + "\n", html, count=1)

    # all.html: ol-li then p outside
    outer = re.compile(
        r"(<p>体系明显偏好以下资产：</p>\s*)"
        r"(?:<ol>\s*<li>[\s\S]*?</li>\s*</ol>\s*<p>[\s\S]*?</p>\s*){4}",
        re.I,
    )
    if outer.search(html):
        return outer.sub(r"\1" + ASSET_BLOCK + "\n", html, count=1)

    # already fixed marker
    if "核心央企、国企、大型金融机构</strong><p>例如大行" in html:
        m = re.search(
            r"<p>体系明显偏好以下资产：</p>\s*<ol class=\"system-enum-list\">[\s\S]*?</ol>",
            html,
        )
        if m:
            return html[: m.start()] + "<p>体系明显偏好以下资产：</p>\n" + ASSET_BLOCK + html[m.end() :]

    return html


def fix_system_questions(html: str) -> str:
    pat = re.compile(
        r"<p>系统要回答：</p>\s*<ol[^>]*>[\s\S]*?</ol>",
        re.I,
    )
    if pat.search(html):
        return pat.sub("<p>系统要回答：</p>\n" + SYSTEM_QUESTIONS, html, count=1)
    return html


def patch_data() -> None:
    html = git_system_html()
    html = fix_system_questions(html)
    html = fix_asset_section(html)
    raw = DATA_JS.read_text(encoding="utf-8")
    data = json.loads(raw.split("=", 1)[1].strip().rstrip(";"))
    data["systemHtml"] = html
    body = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    DATA_JS.write_text(f"window.SHENGSHI_DATA = {body};\n", encoding="utf-8")
    print("data.js restored + fixed")


def patch_all() -> None:
    text = ALL_HTML.read_text(encoding="utf-8")
    # restore system section from fixed data.js for consistency is heavy; patch in place
    text = fix_system_questions(text)
    text = fix_asset_section(text)
    if ".system ol.system-enum-list" not in text:
        text = text.replace(
            ".hidden{display:none!important}",
            ".hidden{display:none!important}" + ENUM_CSS,
            1,
        )
    ALL_HTML.write_text(text, encoding="utf-8")
    print("all.html fixed")


if __name__ == "__main__":
    patch_data()
    patch_all()

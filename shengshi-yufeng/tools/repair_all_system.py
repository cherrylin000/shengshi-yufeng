#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Restore all.html #system section from git and apply list + flowchart fixes."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
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


def git_all() -> str:
    return subprocess.check_output(
        ["git", "-C", str(REPO), "show", "7e0a07f:shengshi-yufeng/all.html"],
        text=True,
        encoding="utf-8",
    )


def extract_system(html: str) -> str:
    m = re.search(
        r'(<section id="system"[^>]*>)([\s\S]*?)(</section>\s*</section>\s*<section id="transcripts")',
        html,
    )
    if not m:
        m = re.search(
            r'(<section id="system"[^>]*>)([\s\S]*?)(</section>\s*<section id="transcripts")',
            html,
        )
    if not m:
        raise SystemExit("system section markers not found")
    return m.group(2)


def fix_lists(body: str) -> str:
    body = re.sub(
        r"<p>系统要回答：</p>\s*<ol[^>]*>[\s\S]*?</ol>",
        "<p>系统要回答：</p>\n" + SYSTEM_QUESTIONS,
        body,
        count=1,
    )
    outer = re.compile(
        r"(<p>体系明显偏好以下资产：</p>\s*)"
        r"(?:<ol>\s*<li>[\s\S]*?</li>\s*</ol>\s*<p>[\s\S]*?</p>\s*){4}",
        re.I,
    )
    if outer.search(body):
        body = outer.sub(r"\1" + ASSET_BLOCK + "\n", body, count=1)
    return body


def ensure_flowcharts(body: str, git_body: str) -> str:
    """Re-attach flowcharts if missing (copy from current all or inject)."""
    for block_id in ["system-flow-overview", "system-flow-main"]:
        if block_id in body:
            continue
        m = re.search(
            rf'<figure class="system-flow[^"]*"[^>]*aria-labelledby="{block_id}"[\s\S]*?</figure>\s*(?:<p class="system-flow-note">[\s\S]*?</p>\s*)?',
            git_body,
        )
        if not m:
            continue
        block = m.group(0)
        if block_id == "system-flow-overview":
            anchor = "<h3>一、底层信念"
            if anchor in body:
                body = body.replace(anchor, block + anchor, 1)
        elif block_id == "system-flow-main":
            body = re.sub(
                r"<h3>十一、体系结构图</h3>\s*<pre>[\s\S]*?</pre>",
                "<h3>十一、体系结构图</h3>\n" + block,
                body,
                count=1,
            )
    return body


def main() -> None:
    git = git_all()
    current = ALL_HTML.read_text(encoding="utf-8")
    git_body = extract_system(git)
    cur_body = extract_system(current)

    body = fix_lists(git_body)
    body = ensure_flowcharts(body, cur_body if "system-flow" in cur_body else git)

    new_system = body
    out = re.sub(
        r'(<section id="system"[^>]*>)[\s\S]*?(</section>\s*(?:</section>\s*)?<section id="transcripts")',
        r"\1" + new_system + r"\2",
        current,
        count=1,
    )
    if ".system ol.system-enum-list" not in out:
        out = out.replace(
            ".hidden{display:none!important}",
            ".hidden{display:none!important}" + ENUM_CSS,
            1,
        )
    ALL_HTML.write_text(out, encoding="utf-8")
    print("all.html system section repaired")


if __name__ == "__main__":
    main()

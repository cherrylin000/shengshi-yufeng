#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Inject system flowchart HTML/CSS into all.html."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ALL_HTML = ROOT / "all.html"

OVERVIEW = [
    "底层信念", "选股·三低一高", "估值·安全边际", "买入·分批",
    "持有·分红攒股", "轮动·再配置", "风控·分散", "心性·纪律",
]
MAIN = [
    "长期闲钱",
    "三低一高筛选",
    "能活、能赚、能分红的核心股权",
    "分批买入 + 分散配置",
    "做股东、吃分红、攒股数",
    "分红再投资 / 配置到更低估资产",
    "估值修复或高估时适度轮动",
    "股数增加 + 现金流增加 + 低/零/负成本股权",
    "家庭被动收入管道与可传承资产",
]

FLOW_CSS = """
.system-flow{margin:22px 0 28px;padding:20px 18px;border:1px solid var(--hairline);background:var(--surface)}
.system-flow-title{margin:0 0 16px;font-family:var(--mono);font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:var(--accent);font-weight:500}
.system-flow-note{margin:14px 0 0;font-size:13px;color:var(--muted);text-align:center}
.system-flow-track{display:flex;flex-direction:column;align-items:stretch;max-width:440px;margin:0 auto}
.system-flow--overview .system-flow-track{max-width:100%}
@media(min-width:900px){.system-flow--overview .system-flow-track{flex-direction:row;flex-wrap:wrap;align-items:center;justify-content:center;gap:0}.system-flow--overview .flow-node{flex:1 1 108px;max-width:132px}.system-flow--overview .flow-connector{width:18px;height:1px;min-height:1px;flex:0 0 18px;margin:0}.system-flow--overview .flow-connector::after{top:50%;bottom:auto;left:auto;right:-4px;transform:translateY(-50%);border:5px solid transparent;border-left-color:var(--accent);border-top-color:transparent}}
.flow-node{padding:12px 14px;border:1px solid var(--hairline);background:var(--canvas);text-align:center;display:grid;gap:4px}
.flow-node--start{border-color:var(--accent)}
.flow-node--end{background:var(--accent);color:var(--canvas);border-color:var(--accent)}
.flow-node--end .flow-node-index{color:#b8c9de}
.flow-node-index{font-family:var(--mono);font-size:10px;letter-spacing:.1em;color:var(--muted)}
.flow-node-label{font-size:14px;line-height:1.45;font-weight:500}
.flow-connector{align-self:center;width:1px;height:18px;background:var(--accent);position:relative;margin:3px auto;flex-shrink:0}
.flow-connector::after{content:"";position:absolute;bottom:-4px;left:50%;transform:translateX(-50%);border:5px solid transparent;border-top-color:var(--accent)}
"""


def build_figure(title: str, steps: list[str], fig_id: str, extra: str = "") -> str:
    parts: list[str] = []
    for i, label in enumerate(steps):
        n = f"{i + 1:02d}"
        cls = ["flow-node"]
        if i == 0:
            cls.append("flow-node--start")
        if i == len(steps) - 1:
            cls.append("flow-node--end")
        parts.append(
            f'<motion.div class="{" ".join(cls)}"><span class="flow-node-index">{n}</span>'
            f'<span class="flow-node-label">{label}</span></motion.div>'
        )
        if i < len(steps) - 1:
            parts.append('<div class="flow-connector" aria-hidden="true"></motion.div>')
    track = "".join(parts).replace("<motion.div", "<div").replace("</motion.div>", "</div>")
    return (
        f'<figure class="system-flow {extra}" aria-labelledby="{fig_id}">'
        f'<figcaption id="{fig_id}" class="system-flow-title">{title}</figcaption>'
        f'<div class="system-flow-track">{track}</motion.div></figure>'
    ).replace("</motion.div>", "</div>")


def main() -> None:
    text = ALL_HTML.read_text(encoding="utf-8")
    if ".system-flow{" in text and "system-flow-overview" in text:
        print("all.html already has flowchart")
        return

    if ".system-flow{" not in text:
        text = text.replace(
            ".hidden{display:none!important}",
            ".hidden{display:none!important}" + FLOW_CSS,
            1,
        )

    overview_html = (
        build_figure("体系全景流程", OVERVIEW, "system-flow-overview", "system-flow--overview")
        + '<p class="system-flow-note">从信念到执行，八个模块串联成完整投资系统。</p>'
    )
    main_html = (
        build_figure("体系主流程", MAIN, "system-flow-main")
        + '<p class="system-flow-note">长期闲钱进入系统，以分红攒股与轮动完成复利闭环。</p>'
    )

    # Insert overview before 一、底层信念
    marker = "<h3>一、底层信念"
    if marker in text and "system-flow-overview" not in text:
        text = text.replace(marker, overview_html + marker, 1)

    # Replace pre under 十一、体系结构图
    pre_pat = re.compile(
        r"(<h3>十一、体系结构图</h3>)\s*<pre>.*?</pre>",
        re.S,
    )
    if pre_pat.search(text):
        text = pre_pat.sub(r"\1\n" + main_html, text, count=1)

    ALL_HTML.write_text(text, encoding="utf-8")
    print("patched", ALL_HTML)


if __name__ == "__main__":
    main()

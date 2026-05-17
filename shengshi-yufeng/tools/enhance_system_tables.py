#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Convert structured blocks in systemHtml to portable HTML tables."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_JS = ROOT / "data.js"
ALL_HTML = ROOT / "all.html"

FLOW_OVERVIEW = [
    "底层信念", "选股·三低一高", "估值·安全边际", "买入·分批",
    "持有·分红攒股", "轮动·再配置", "风控·分散", "心性·纪律",
]
FLOW_MAIN = [
    "长期闲钱", "三低一高筛选", "能活、能赚、能分红的核心股权",
    "分批买入 + 分散配置", "做股东、吃分红、攒股数",
    "分红再投资 / 配置到更低估资产", "估值修复或高估时适度轮动",
    "股数增加 + 现金流增加 + 低/零/负成本股权",
    "家庭被动收入管道与可传承资产",
]
QUESTIONS = [
    "买什么", "为什么买", "什么时候买", "买多少",
    "怎么持有", "什么时候轮动或卖出", "出错怎么办",
]
ASSETS = [
    ("核心央企、国企、大型金融机构", "例如大行、保险、再保险、不良资产处置机构等。逻辑是国家信用、行业地位、规模优势、长期存在概率较高。"),
    ("国计民生行业", "能源、石化、电信、电力、水电、交通基础设施、铁路、高速、港口、机场等。这些行业变化慢、需求长期存在、现金流较稳定。"),
    ("成熟高分红行业", "增速未必高，但利润真实，分红稳定，估值低，能给小股东现金回报。"),
    ("低估的硬资产和现金流资产", "资产真实、行业长寿、价格低于保守价值。"),
]
SAN_DI_ROWS = [
    ("低市净率", "价格相对净资产便宜", "提供资产折价和安全边际"),
    ("低市盈率", "价格相对利润便宜", "提供盈利收益率保护"),
    ("低换手/低关注/月线低位", "市场冷清、没人追捧", "避免热门高估，寻找均值回归空间"),
    ("高股息率", "小股东能拿到现金流", "提供分红复投和持有底气"),
]


def table(headers: list[str], rows: list[tuple], caption: str = "") -> str:
    cap = f"<caption>{caption}</caption>\n" if caption else ""
    head = "<thead><tr>" + "".join(f'<th scope="col">{h}</th>' for h in headers) + "</tr></thead>"
    body_rows = []
    for row in rows:
        body_rows.append("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>")
    body = "<tbody>\n" + "\n".join(body_rows) + "\n</tbody>"
    return (
        f'<table class="system-table" border="1" cellpadding="8" cellspacing="0" width="100%">\n'
        f"{cap}{head}\n{body}\n</table>"
    )


def numbered_table(headers: list[str], items: list[tuple]) -> str:
    rows = [(str(i), *rest) for i, rest in enumerate(items, 1)]
    return table(["序号", *headers], rows)


def strengthen_tables(html: str) -> str:
    def repl(m: re.Match[str]) -> str:
        tag = m.group(0)
        if "system-table" in tag:
            return tag
        return tag.replace("<table", '<table class="system-table" border="1" cellpadding="8" cellspacing="0" width="100%"', 1)

    return re.sub(r"<table\b[^>]*>", repl, html)


def replace_enum_lists(html: str) -> str:
    questions_tbl = numbered_table(["要点"], [(q,) for q in QUESTIONS])
    html = re.sub(
        r"<p>系统要回答：</p>\s*<ol[^>]*>[\s\S]*?</ol>",
        "<p>系统要回答：</p>\n" + questions_tbl,
        html,
        count=1,
    )
    assets_tbl = numbered_table(
        ["资产类型", "说明"],
        [(t, d) for t, d in ASSETS],
    )
    html = re.sub(
        r"<p>体系明显偏好以下资产：</p>\s*<ol[^>]*>[\s\S]*?</ol>",
        "<p>体系明显偏好以下资产：</p>\n" + assets_tbl,
        html,
        count=1,
    )
    return html


def replace_principles_ol(html: str) -> str:
    pat = re.compile(
        r"(<h[23][^>]*>十三、最浓缩的十条原则</h[23]>)\s*<ol>([\s\S]*?)</ol>",
        re.I,
    )

    def repl(m: re.Match[str]) -> str:
        items = re.findall(r"<li>([\s\S]*?)</li>", m.group(2))
        if len(items) < 5:
            return m.group(0)
        rows = [(it.strip(),) for it in items]
        tbl = numbered_table(["原则"], rows)
        return m.group(1) + "\n" + tbl

    return pat.sub(repl, html)


def replace_overview_flow_figure(html: str) -> str:
    overview_tbl = numbered_table(["模块"], [(m,) for m in FLOW_OVERVIEW])
    overview_block = (
        f'<h3 class="system-table-title">体系全景流程</h3>\n{overview_tbl}\n'
        '<p class="system-table-note">从信念到执行，八个模块串联成完整投资系统。</p>\n'
    )
    if "system-flow--overview" in html:
        return re.sub(
            r'<figure class="system-flow system-flow--overview"[\s\S]*?</figure>\s*'
            r'(?:<p class="system-flow-note">[\s\S]*?</p>\s*)?',
            overview_block,
            html,
            count=1,
        )
    return html


def fix_markdown_pipe_table(html: str) -> str:
    pat = (
        r"<p>\|\s*维度\s*\|\s*含义\s*\|\s*作用\s*\|</p>\s*"
        r"<p>\|[-\s|]+\|</p>\s*"
        r"((?:<p>\|[^<]+\|</p>\s*)+)"
    )

    def repl(_: re.Match[str]) -> str:
        tbl = table(["维度", "含义", "作用"], SAN_DI_ROWS)
        return tbl + "\n"

    return re.sub(pat, repl, html, count=1)


def chapter_eleven_block(html: str) -> str:
    main_tbl = numbered_table(["环节"], [(s,) for s in FLOW_MAIN])
    main_inner = (
        f'<h3 class="system-table-title">体系主流程</h3>\n{main_tbl}\n'
        '<p class="system-table-note">长期闲钱进入系统，以分红攒股与轮动完成复利闭环。</p>\n'
    )
    if re.search(r"<h2[^>]*>十二、体系边界</h2>", html):
        return f'<h2 id="十一-体系结构图">十一、体系结构图</h2>\n{main_inner}'
    return f"<h3>十一、体系结构图</h3>\n{main_inner}"


def fix_chapter_eleven(html: str) -> str:
    chapter = chapter_eleven_block(html)

    html = re.sub(
        r"<h3 class=\"system-table-title\">体系主流程</h3>\s*"
        r'<table class="system-table"[\s\S]*?</table>\s*'
        r'<p class="system-table-note">[\s\S]*?</p>\s*',
        "",
        html,
        count=1,
    )
    if re.search(r"<h[23][^>]*>十一、体系结构图</h[23]>", html, re.I):
        html = re.sub(
            r"(<h[23][^>]*>十一、体系结构图</h[23]>)\s*"
            r"(?:<pre>[\s\S]*?</pre>|"
            r'<figure class="system-flow[\s\S]*?</figure>\s*'
            r'(?:<p class="system-flow-note">[\s\S]*?</p>\s*)?|'
            r'<h3 class="system-table-title">体系主流程</h3>[\s\S]*?'
            r'<p class="system-table-note">[\s\S]*?</p>\s*)*',
            chapter,
            html,
            count=1,
        )
    elif "十二、体系边界" in html and "十一、体系结构图" not in html:
        html = re.sub(
            r"(<h[23][^>]*>十二、体系边界</h[23]>)",
            chapter + r"\1",
            html,
            count=1,
        )
    return html


def replace_checklists(html: str) -> str:
    """Each h3 under 十、执行清单 + following ul → table."""
    marker = re.search(r"<h[23][^>]*>十、可?执行清单</h[23]>", html, re.I)
    if not marker:
        return html
    start = marker.start()
    end_m = re.search(r"<h[23][^>]*>十一、", html[start:], re.I)
    end = start + end_m.start() if end_m else len(html)
    chunk = html[start:end]

    def repl_block(m: re.Match[str]) -> str:
        title = re.sub(r"<[^>]+>", "", m.group(1)).strip()
        items = re.findall(r"<li>([\s\S]*?)</li>", m.group(2))
        if not items:
            return m.group(0)
        rows = [(it.strip(),) for it in items]
        tbl = numbered_table(["检查项"], rows)
        return m.group(0).split("<ul>")[0].replace(
            m.group(1), m.group(1)
        )  # noqa - use structured rebuild
        # rebuild: keep h3, replace ul with table
        h3 = m.group(0)[: m.group(0).find("<ul>")]
        return h3 + tbl

    chunk2 = re.sub(
        r"(<h[34][^>]*>[\s\S]*?</h[34]>)\s*<ul>([\s\S]*?)</ul>",
        lambda m: (
            m.group(1)
            + "\n"
            + numbered_table(
                ["检查项"],
                [(re.sub(r"\s+", " ", it.strip()),) for it in re.findall(r"<li>([\s\S]*?)</li>", m.group(2))],
            )
        ),
        chunk,
    )
    return html[:start] + chunk2 + html[end:]


def replace_boundary_lists(html: str) -> str:
    def ul_to_table(ul_html: str, caption: str) -> str:
        items = re.findall(r"<li>([\s\S]*?)</li>", ul_html)
        if not items:
            return ul_html
        rows = [(it.strip(),) for it in items]
        return table(["要点"], rows, caption=caption)

    html = re.sub(
        r"<p>这套体系不追求：</p>\s*<ul>([\s\S]*?)</ul>",
        lambda m: "<p>这套体系不追求：</p>\n" + ul_to_table(f"<ul>{m.group(1)}</ul>", "不追求"),
        html,
        count=1,
    )
    html = re.sub(
        r"<p>这套体系追求：</p>\s*<ul>([\s\S]*?)</ul>",
        lambda m: "<p>这套体系追求：</p>\n" + ul_to_table(f"<ul>{m.group(1)}</ul>", "追求"),
        html,
        count=1,
    )
    return html


def inject_flow_tables(html: str) -> str:
    overview_tbl = numbered_table(["模块"], [(m,) for m in FLOW_OVERVIEW])
    overview_block = (
        f'<h3 class="system-table-title">体系全景流程</h3>\n{overview_tbl}\n'
        '<p class="system-table-note">从信念到执行，八个模块串联成完整投资系统。</p>\n'
    )
    main_block = chapter_eleven_block(html)

    if "体系全景流程" not in html and "system-table-title" not in html:
        html = re.sub(
            r"(<h[23][^>]*>一、底层信念[^<]*</h[23]>)",
            overview_block + r"\1",
            html,
            count=1,
        )

    html = re.sub(
        r"<h[23][^>]*>十一、体系结构图</h[23]>\s*(?:<pre>[\s\S]*?</pre>|"
        r'<figure class="system-flow[\s\S]*?</figure>\s*'
        r'(?:<p class="system-flow-note">[\s\S]*?</p>\s*)?)*',
        main_block,
        html,
        count=1,
    )
    return html


def transform(html: str) -> str:
    html = strengthen_tables(html)
    html = replace_overview_flow_figure(html)
    html = fix_markdown_pipe_table(html)
    html = replace_enum_lists(html)
    html = replace_principles_ol(html)
    html = replace_checklists(html)
    html = replace_boundary_lists(html)
    html = inject_flow_tables(html)
    html = fix_chapter_eleven(html)
    return html


ALL_TABLE_CSS = """
.system-table,.system table{width:100%;max-width:100%;border-collapse:collapse;margin:16px 0 20px;font-size:14px;line-height:1.5}
.system-table caption,.system table caption{caption-side:top;text-align:left;font-family:var(--mono);font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--accent);padding:0 0 8px}
.system-table th,.system-table td,.system th,.system td{border:1px solid var(--hairline);padding:10px 12px;text-align:left;vertical-align:top}
.system-table th,.system th{background:var(--surface);font-weight:500;color:var(--accent)}
.system-table-title{margin:24px 0 8px;font-size:18px;font-weight:500;color:var(--accent)}
.system-table-note{margin:0 0 16px;font-size:13px;color:var(--muted)}
@media(max-width:640px){.system-table,.system table{display:block;overflow-x:auto}}
"""


def inject_all_css(text: str) -> str:
    if ".system-table-title" in text:
        return text
    return text.replace("</style>", ALL_TABLE_CSS + "</style>", 1)


def patch_data_js() -> None:
    raw = DATA_JS.read_text(encoding="utf-8")
    data = json.loads(raw.split("=", 1)[1].strip().rstrip(";"))
    data["systemHtml"] = transform(data["systemHtml"])
    body = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    DATA_JS.write_text(f"window.SHENGSHI_DATA = {body};\n", encoding="utf-8")
    print("data.js: systemHtml → tables")


def patch_all_html() -> None:
    text = ALL_HTML.read_text(encoding="utf-8")
    m = re.search(
        r'(<section id="system"[^>]*>)([\s\S]*?)(</section>\s*(?:</section>\s*)?<section id="transcripts")',
        text,
    )
    if not m:
        raise SystemExit("all.html: system section not found")
    body = transform(m.group(2))
    body = re.sub(r"</section>\s*</section>\s*<section id=\"transcripts\"", "</section>\n<section id=\"transcripts\"", body, count=1)
    text = text[: m.start(2)] + body + text[m.end(2) :]
    text = inject_all_css(text)
    ALL_HTML.write_text(text, encoding="utf-8")
    print("all.html: system section → tables")


if __name__ == "__main__":
    patch_data_js()
    patch_all_html()

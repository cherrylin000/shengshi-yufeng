#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Convert structured blocks in systemHtml to portable HTML tables."""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

from data_bundle import load_data, save_data  # noqa: E402
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


def _dl_row(headers: list[str], cells: tuple[str, ...]) -> str:
    h = list(headers)
    c = [str(cell) for cell in cells]
    if h and h[0] == "序号" and len(c) == 2:
        return (
            '<div class="system-dl-row">'
            f'<dt class="system-dl-term system-dl-term--index">{c[0]}</dt>'
            f'<dd class="system-dl-desc">{c[1]}</dd>'
            "</div>"
        )
    start = 1 if h and h[0] == "序号" else 0
    h = h[start:]
    c = c[start:]
    if not c:
        return ""
    if len(c) == 1:
        label = html.escape(h[0]) if h else ""
        return (
            '<div class="system-dl-row">'
            f'<dt class="system-dl-term">{label}</dt>'
            f'<dd class="system-dl-desc">{c[0]}</dd>'
            "</div>"
        )
    if len(c) == 2:
        return (
            '<div class="system-dl-row">'
            f'<dt class="system-dl-term">{_clean_cell(c[0])}</dt>'
            f'<dd class="system-dl-desc">{_clean_cell(c[1])}</dd>'
            "</div>"
        )
    cls = f"system-dl-row system-dl-row--cols-{len(c)}"
    parts = [f'<dt class="system-dl-term">{_clean_cell(c[0])}</dt>']
    parts.extend(f'<dd class="system-dl-desc">{_clean_cell(part)}</dd>' for part in c[1:])
    return f'<div class="{cls}">' + "".join(parts) + "</div>"


def definition_list(headers: list[str], rows: list[tuple], caption: str = "") -> str:
    cap_html = (
        f'<p class="system-dl-caption">{html.escape(caption)}</p>\n' if caption else ""
    )
    body = "\n".join(_dl_row(headers, row) for row in rows if _dl_row(headers, row))
    dl_cls = "system-dl system-dl--has-index" if headers and headers[0] == "序号" else "system-dl"
    return (
        f'<div class="system-dl-flow">\n{cap_html}'
        f'<dl class="{dl_cls}">\n{body}\n</dl>\n</div>'
    )


def table(headers: list[str], rows: list[tuple], caption: str = "") -> str:
    return definition_list(headers, rows, caption)


def numbered_table(headers: list[str], items: list[tuple]) -> str:
    rows = [(str(i), *rest) for i, rest in enumerate(items, 1)]
    return definition_list(["序号", *headers], rows)


def strengthen_tables(html: str) -> str:
    def repl(m: re.Match[str]) -> str:
        tag = m.group(0)
        if "system-table" in tag:
            return tag
        return tag.replace("<table", '<table class="system-table" border="1" cellpadding="8" cellspacing="0" width="100%"', 1)

    return re.sub(r"<table\b[^>]*>", repl, html)


def assets_table_html() -> str:
    return table(
        ["资产类型", "说明"],
        [(title, desc) for title, desc in ASSETS],
    )


def _clean_cell(text: str) -> str:
    s = str(text).strip()
    m = re.fullmatch(r"\['(.*)'\]", s, re.S) or re.fullmatch(r'\["(.*)"\]', s, re.S)
    return m.group(1) if m else s


def strip_malformed_assets_prefix(html: str) -> str:
    """Remove orphan <tr> rows and broken table fragments before the assets dl-flow."""
    return re.sub(
        r"(<h3[^>]*>3\.\s*偏好的资产类型</h3>\s*)"
        r"(?:(?:<tr>[\s\S]*?</tr>\s*)+"
        r"(?:<table\b[\s\S]*?(?:</table>|(?=<p>体系明显偏好|<div class=\"system-dl-flow)))"
        r")?",
        r"\1",
        html,
        count=1,
    )


def normalize_assets_section(html: str) -> str:
    if "体系明显偏好以下资产" not in html:
        return html
    block = "<p>体系明显偏好以下资产：</p>\n" + assets_table_html() + "\n"
    pat = (
        r"<p>体系明显偏好以下资产：</p>"
        r"[\s\S]*?"
        r"(?=<p>代表文稿|<p>但是|<h2\b|<h3\b|<blockquote|<ul\b|<ol\b|\Z)"
    )
    return re.sub(pat, block, html, count=1)


def strip_assets_table_serial(html: str) -> str:
    """Ensure preferred-assets block is a single two-column definition list."""
    return normalize_assets_section(html)


def replace_enum_lists(html: str) -> str:
    questions_tbl = numbered_table(["要点"], [(q,) for q in QUESTIONS])
    html = re.sub(
        r"<p>系统要回答：</p>\s*<ol[^>]*>[\s\S]*?</ol>",
        "<p>系统要回答：</p>\n" + questions_tbl,
        html,
        count=1,
    )
    assets_tbl = assets_table_html()
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


def overview_flow_block() -> str:
    overview_tbl = numbered_table(["模块"], [(m,) for m in FLOW_OVERVIEW])
    return (
        f'<h3 class="system-table-title">体系全景流程</h3>\n{overview_tbl}\n'
        '<p class="system-table-note">从信念到执行，八个模块串联成完整投资系统。</p>\n'
    )


OVERVIEW_NOTE_TEXT = "从信念到执行，八个模块串联成完整投资系统。"


def _overview_trailing_junk() -> str:
    note = re.escape(OVERVIEW_NOTE_TEXT)
    return (
        rf'(?:\s*<p class="system-(?:flow|table)-note">{note}</p>)*'
        r'(?:\s*<div class="system-dl-row system-dl-row--solo">[\s\S]*?</div>)*'
        r'(?:\s*</dl>\s*</div>\s*)*'
    )


def normalize_overview_section(html: str) -> str:
    if "体系全景流程" not in html:
        return html
    overview_block = overview_flow_block()
    pat = (
        r'<h3 class="system-table-title">体系全景流程</h3>'
        r'[\s\S]*?'
        r'(?=<h2\b)'
    )
    return re.sub(pat, overview_block + "\n", html, count=1)


def replace_overview_flow_figure(html: str) -> str:
    overview_block = overview_flow_block()
    junk = _overview_trailing_junk()
    if "system-flow--overview" in html:
        return re.sub(
            r'<figure class="system-flow system-flow--overview"[\s\S]*?</figure>'
            + junk,
            overview_block,
            html,
            count=1,
        )
    if "体系全景流程" in html:
        dl_flow = (
            r'<div class="system-dl-flow">\s*'
            r'<dl class="system-dl[^"]*"[\s\S]*?</dl>\s*</div>'
        )
        table = r'<table class="system-table"[\s\S]*?</table>'
        section = (
            r'<h3 class="system-table-title">体系全景流程</h3>\s*'
            rf'(?:{dl_flow}|{table})'
            + junk
        )
        html, n = re.subn(section, overview_block, html, count=1)
        if n:
            return html
        return normalize_overview_section(html)
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


def _flow_nodes_html(steps: list[str]) -> str:
    nodes: list[str] = []
    last = len(steps) - 1
    for i, label in enumerate(steps):
        n = str(i + 1).zfill(2)
        cls_parts = ["flow-node"]
        if i == 0:
            cls_parts.append("flow-node--start")
        if i == last:
            cls_parts.append("flow-node--end")
        cls = " ".join(cls_parts)
        connector = (
            '<div class="flow-connector" aria-hidden="true"></div>'
            if i < last
            else ""
        )
        nodes.append(
            f'<div class="{cls}">'
            f'<span class="flow-node-index">{n}</span>'
            f'<span class="flow-node-label">{html.escape(label)}</span>'
            f"</div>{connector}"
        )
    return "".join(nodes)


def flow_track_html(
    steps: list[str],
    *,
    track_class: str = "system-flow-track system-diagram-flow",
    footer_html: str = "",
    aria_label: str = "",
) -> str:
    aria = f' aria-label="{html.escape(aria_label)}"' if aria_label else ""
    return (
        f'<div class="{track_class}"{aria}>'
        f"{_flow_nodes_html(steps)}"
        f"</div>{footer_html}"
    )


def flow_figure_html(
    title: str,
    steps: list[str],
    fig_id: str,
    extra_class: str = "",
    *,
    include_title: bool = True,
    footer_html: str = "",
) -> str:
    flow_cls = "system-flow " + extra_class if extra_class else "system-flow"
    cap = (
        f'<figcaption id="{fig_id}" class="system-flow-title">{html.escape(title)}</figcaption>'
        if include_title and title
        else ""
    )
    if include_title and title:
        aria = f' aria-labelledby="{fig_id}"'
    elif title:
        aria = f' aria-label="{html.escape(title)}"'
    else:
        aria = ""
    return (
        f'<figure class="{flow_cls.strip()}"{aria}>'
        f"{cap}"
        f'<div class="system-flow-track">{_flow_nodes_html(steps)}</div>'
        f"{footer_html}"
        f"</figure>"
    )


def diagram_main_flow_inner() -> str:
    note = '<p class="system-flow-note">长期闲钱进入系统，以分红攒股与轮动完成复利闭环。</p>'
    return flow_track_html(FLOW_MAIN, footer_html=note, aria_label="体系主流程")


def diagram_section_block() -> str:
    return f'<h2 id="体系结构图">体系结构图</h2>\n{diagram_main_flow_inner()}'


def normalize_diagram_section(html: str) -> str:
    if "体系结构图" not in html:
        return html
    block = diagram_section_block()
    pat = (
        r'<h2[^>]*>体系结构图</h2>'
        r"[\s\S]*?"
        r"(?=<h2[^>]*>体系边界|<h2[^>]*>十二、|\Z)"
    )
    return re.sub(pat, block + "\n", html, count=1)


def chapter_eleven_block(html: str) -> str:
    inner = diagram_main_flow_inner()
    if re.search(r"<h2[^>]*>十二、体系边界</h2>", html):
        return f'<h2 id="十一-体系结构图">十一、体系结构图</h2>\n{inner}'
    return f"<h3>十一、体系结构图</h3>\n{inner}"


def fix_chapter_eleven(html: str) -> str:
    chapter = chapter_eleven_block(html)

    html = re.sub(
        r"<h3 class=\"system-table-title\">体系主流程</h3>\s*"
        r"(?:<div class=\"system-dl-flow\">[\s\S]*?</div>|"
        r'<table class="system-table"[\s\S]*?</table>|'
        r'<figure class="system-flow[\s\S]*?</figure>|'
        r'<div class="system-flow-track system-diagram-flow[\s\S]*?</div>)\s*'
        r'<p class="system-(?:table|flow)-note">[\s\S]*?</p>\s*',
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
            r'<div class="system-flow-track system-diagram-flow[\s\S]*?</div>\s*'
            r'(?:<p class="system-flow-note">[\s\S]*?</p>\s*)?|'
            r'<h3 class="system-table-title">体系主流程</h3>[\s\S]*?'
            r'<p class="system-(?:table|flow)-note">[\s\S]*?</p>\s*)*',
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


CHECKLIST_CHEVRON = (
    '<svg class="system-checklist-chevron" width="20" height="20" viewBox="0 0 24 24" '
    'fill="none" stroke="currentColor" aria-hidden="true" focusable="false">'
    '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/>'
    "</svg>"
)


def checklist_fieldset(items: list[str], group_id: str) -> str:
    options = []
    for i, item in enumerate(items):
        cid = f"{group_id}-item-{i + 1}"
        options.append(
            f'<label class="system-checklist-option" for="{cid}">'
            f'<input type="checkbox" class="system-checklist-input" id="{cid}" />'
            f'<span class="system-checklist-option-text">{html.escape(item)}</span>'
            f"</label>"
        )
    return (
        '<fieldset class="system-checklist-fieldset">'
        '<legend class="sr-only">检查项</legend>'
        f'<div class="system-checklist-options">{"".join(options)}</div>'
        "</fieldset>"
    )


def checklist_details(title_html: str, panel_html: str, *, open_first: bool = False) -> str:
    title = re.sub(r"<[^>]+>", "", title_html).strip()
    open_attr = " open" if open_first else ""
    return (
        f'<details class="system-checklist-item"{open_attr}>'
        f'<summary class="system-checklist-summary">'
        f'<span class="system-checklist-label">{html.escape(title)}</span>{CHECKLIST_CHEVRON}</summary>'
        f'<div class="system-checklist-panel">{panel_html}</div>'
        f"</details>"
    )


def replace_checklists(html: str) -> str:
    """Each h3 under 十、执行清单 + following ul → accordion details + table."""
    marker = re.search(r"<h[23][^>]*>十、可?执行清单</h[23]>", html, re.I)
    if not marker:
        return html
    start = marker.start()
    end_m = re.search(r"<h[23][^>]*>十一、", html[start:], re.I)
    end = start + end_m.start() if end_m else len(html)
    chunk = html[start:end]

    details_blocks: list[str] = []

    def repl_block(m: re.Match[str]) -> str:
        items = re.findall(r"<li>([\s\S]*?)</li>", m.group(2))
        if not items:
            return m.group(0)
        plain_items = [re.sub(r"\s+", " ", it.strip()) for it in items]
        fieldset = checklist_fieldset(plain_items, f"checklist-{len(details_blocks)}")
        details_blocks.append(
            checklist_details(m.group(1), fieldset, open_first=len(details_blocks) == 0)
        )
        return ""

    chunk_body = re.sub(
        r"(<h[34][^>]*>[\s\S]*?</h[34]>)\s*<ul>([\s\S]*?)</ul>",
        repl_block,
        chunk,
    )
    if not details_blocks:
        return html
    accordion = '<div class="system-checklist-accordion">' + "".join(details_blocks) + '</div>'
    chunk2 = re.sub(
        r"<h[23][^>]*>十、可?执行清单</h[23]>",
        lambda m: m.group(0) + "\n" + accordion,
        chunk_body,
        count=1,
        flags=re.I,
    )
    return html[:start] + chunk2 + html[end:]


def replace_boundary_lists(html: str) -> str:
    def ul_items(ul_html: str) -> list[str]:
        return [
            re.sub(r"[；;]\s*$", "", it.strip())
            for it in re.findall(r"<li>([\s\S]*?)</li>", ul_html)
        ]

    def col(title: str, items: list[str]) -> str:
        lis = "".join(f"<li>{it}</li>" for it in items)
        return (
            f'<div class="system-boundary-col">'
            f'<h3 class="system-boundary-heading">{title}</h3>'
            f'<ul class="system-boundary-list">{lis}</ul>'
            f"</div>"
        )

    m_avoid = re.search(r"<p>这套体系不追求：</p>\s*<ul>([\s\S]*?)</ul>", html)
    m_pursue = re.search(r"<p>这套体系追求：</p>\s*<ul>([\s\S]*?)</ul>", html)
    if m_avoid and m_pursue:
        avoid = ul_items(m_avoid.group(1))
        pursue = ul_items(m_pursue.group(1))
        grid = f'<div class="system-boundary-grid">{col("不追求", avoid)}{col("追求", pursue)}</div>'
        html = re.sub(
            r"<p>这套体系不追求：</p>\s*<ul>[\s\S]*?</ul>\s*"
            r"<p>这套体系追求：</p>\s*<ul>[\s\S]*?</ul>",
            grid,
            html,
            count=1,
        )
    return html


def inject_flow_tables(html: str) -> str:
    overview_block = overview_flow_block()
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


INVESTOR_NICKNAMES: list[tuple[str, str]] = [
    ("格雷厄姆", "祖师爷"),
    ("巴菲特", "巴老"),
    ("芒格", "芒格老"),
    ("施洛斯", "大师兄"),
    ("西格尔", "西格尔教授"),
]


def annotate_investor_nicknames(html: str) -> str:
    for name, nick in INVESTOR_NICKNAMES:
        html = re.sub(
            rf"<li>{re.escape(name)}(?!（)(：)",
            f"<li>{name}（{nick}）：",
            html,
        )
    html = re.sub(r"<li>卡拉曼(：)", "<li>塞思·卡拉曼：", html)
    return html


def transform(html: str) -> str:
    html = strengthen_tables(html)
    html = replace_overview_flow_figure(html)
    html = fix_markdown_pipe_table(html)
    html = replace_enum_lists(html)
    html = strip_malformed_assets_prefix(html)
    html = strip_assets_table_serial(html)
    html = replace_principles_ol(html)
    html = replace_checklists(html)
    html = replace_boundary_lists(html)
    html = inject_flow_tables(html)
    html = fix_chapter_eleven(html)
    html = normalize_overview_section(html)
    html = normalize_assets_section(html)
    html = normalize_diagram_section(html)
    html = annotate_investor_nicknames(html)
    return html


def patch_data_js() -> None:
    import sys

    site_dir = Path(__file__).resolve().parent
    if str(site_dir) not in sys.path:
        sys.path.insert(0, str(site_dir))
    from split_system_sections import build_sections, merge_monolithic_if_needed

    data = load_data()
    html = merge_monolithic_if_needed(data)
    html = transform(html)
    sections = build_sections(html)
    data["systemSections"] = sections
    data["systemHtml"] = sections["core"]
    save_data(data)
    print("data-index.js: systemHtml → tables + systemSections split")


if __name__ == "__main__":
    patch_data_js()

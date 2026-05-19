#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Split systemHtml into core + standalone sections; sync from investment_system.md markers."""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DATA_JS = REPO / "data.js"
SYSTEM_MD = REPO / "content" / "investment_system.md"

H2 = re.compile(r"(<h2[^>]*>)([\s\S]*?)(</h2>)", re.I)
CHAPTER = re.compile(r"^[一二三四五六七八九十]+、")


def load_data() -> dict:
    raw = DATA_JS.read_text(encoding="utf-8")
    payload = raw.removeprefix("window.SHENGSHI_DATA = ").strip().rstrip(";")
    return json.loads(payload)


def save_data(data: dict) -> None:
    body = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    DATA_JS.write_text(f"window.SHENGSHI_DATA = {body};\n", encoding="utf-8")


def merge_monolithic_if_needed(data: dict) -> str:
    """Use full systemHtml when it still contains split chapters (pre-split blob)."""
    html = data.get("systemHtml", "")
    sections = data.get("systemSections") or {}
    monolithic = "八、宏观" in html and "九、心法" in html
    if monolithic:
        return html
    if sections.get("core"):
        return "".join(
            sections.get(k, "")
            for k in ("core", "macro", "checklist", "diagram", "boundary")
        )
    return html


def strip_tags(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s).strip()


def split_html_by_h2(html: str) -> list[tuple[str, str]]:
    """Return [(heading_text, block_html_including_h2), ...] and preamble before first h2."""
    parts = re.split(r"(?=<h2\b)", html, flags=re.I)
    preamble = parts[0] if parts else ""
    blocks: list[tuple[str, str]] = []
    if preamble.strip():
        blocks.append(("__preamble__", preamble))
    for part in parts[1:]:
        m = H2.match(part)
        if not m:
            continue
        title = strip_tags(m.group(0))
        blocks.append((title, part))
    return blocks


def classify(title: str) -> str:
    if title == "__preamble__":
        return "preamble"
    if "宏观框架" in title or title.startswith("八、宏观"):
        return "macro"
    if "心法" in title or title.startswith("九、心法"):
        return "mindset"
    if "可执行清单" in title or title.startswith("十、"):
        return "checklist"
    if "体系结构图" in title or title.startswith("十一、"):
        return "diagram"
    if "体系边界" in title or title.startswith("十二、"):
        return "boundary"
    if "最浓缩" in title or title.startswith("十三、"):
        return "drop"
    if CHAPTER.match(title) or title in ("一句话总纲", "盛世裕丰投资体系整理"):
        return "core"
    return "core"


def renumber_mindset_block(block: str) -> str:
    block = re.sub(
        r"<h2([^>]*)>[\s\S]*?心法[\s\S]*?</h2>",
        '<h2 id="八-心法与训练-投资是一场认知和品性的修行">八、心法与训练：投资是一场认知和品性的修行</h2>',
        block,
        count=1,
        flags=re.I,
    )
    return block


def strip_chapter_prefix(block: str, new_title: str, new_id: str) -> str:
    return re.sub(
        r"<h2[^>]*>[\s\S]*?</h2>",
        f'<h2 id="{new_id}">{new_title}</h2>',
        block,
        count=1,
        flags=re.I,
    )


def build_sections(html: str) -> dict[str, str]:
    buckets: dict[str, list[str]] = {
        "core": [],
        "macro": [],
        "checklist": [],
        "diagram": [],
        "boundary": [],
    }
    for title, block in split_html_by_h2(html):
        kind = classify(title)
        if kind == "drop":
            continue
        if kind == "mindset":
            buckets["core"].append(renumber_mindset_block(block))
            continue
        if kind == "macro":
            buckets["macro"].append(
                strip_chapter_prefix(
                    block,
                    "宏观框架：宏观是背景，不是短线指令",
                    "宏观框架-宏观是背景-不是短线指令",
                )
            )
            continue
        if kind == "checklist":
            buckets["checklist"].append(
                strip_chapter_prefix(block, "可执行清单", "可执行清单")
            )
            continue
        if kind == "diagram":
            buckets["diagram"].append(
                strip_chapter_prefix(block, "体系结构图", "体系结构图")
            )
            continue
        if kind == "boundary":
            buckets["boundary"].append(
                strip_chapter_prefix(block, "体系边界", "体系边界")
            )
            continue
        buckets["core"].append(block)

    # If 八宏观 still in core (old order), move to macro
    core_html = "".join(buckets["core"])
    if "宏观框架" in core_html and not buckets["macro"]:
        reb = []
        for title, block in split_html_by_h2(core_html):
            if classify(title) == "macro":
                buckets["macro"].append(
                    strip_chapter_prefix(
                        block,
                        "宏观框架：宏观是背景，不是短线指令",
                        "宏观框架-宏观是背景-不是短线指令",
                    )
                )
            elif classify(title) != "drop":
                reb.append(block)
        buckets["core"] = reb

    return {k: "".join(v).strip() for k, v in buckets.items() if "".join(v).strip()}


def main() -> None:
    data = load_data()
    html = merge_monolithic_if_needed(data)
    sections = build_sections(html)
    data["systemSections"] = sections
    data["systemHtml"] = sections["core"]
    save_data(data)
    for key, val in sections.items():
        print(f"  {key}: {len(val)} chars")
    print(f"Updated {DATA_JS}")


if __name__ == "__main__":
    main()

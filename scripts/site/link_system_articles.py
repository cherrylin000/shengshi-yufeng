#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Point 代表文稿 ximalaya links to content/article.html in systemHtml / markdown."""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DATA_JS = REPO / "data.js"
SYSTEM_MD = REPO / "content" / "investment_system.md"

SOUND_HREF = re.compile(
    r'(<a\b[^>]*\bhref=")https://www\.ximalaya\.com/sound/(\d+)("[^>]*>)',
    re.I,
)
MD_LINK = re.compile(
    r'\[([^\]]+)\]\(https://www\.ximalaya\.com/sound/(\d+)\)',
)
ARTICLE_HREF = re.compile(
    r'(<a\b[^>]*\bhref=")content/article\.html\?index=(\d+)("[^>]*>)([^<]*)(</a>)',
    re.I,
)
MD_ARTICLE = re.compile(r'\[([^\]]+)\]\(content/article\.html\?index=(\d+)\)')
INDEX_PREFIX = re.compile(r"^\d{3}\s*·\s*")


def label_index(n: int) -> str:
    return f"{int(n):03d} · "


def rewrite_html_labels(html: str) -> str:
    def repl(m: re.Match[str]) -> str:
        idx = int(m.group(2))
        text = m.group(4).strip()
        if INDEX_PREFIX.match(text):
            return m.group(0)
        return f"{m.group(1)}content/article.html?index={idx}{m.group(3)}{label_index(idx)}{text}{m.group(5)}"

    return ARTICLE_HREF.sub(repl, html)


def rewrite_markdown_labels(text: str) -> str:
    def repl(m: re.Match[str]) -> str:
        title, idx_s = m.group(1), m.group(2)
        if INDEX_PREFIX.match(title.strip()):
            return m.group(0)
        idx = int(idx_s)
        return f"[{label_index(idx)}{title}](content/article.html?index={idx})"

    return MD_ARTICLE.sub(repl, text)


def build_maps(tracks: list[dict]) -> tuple[dict[str, int], dict[str, int]]:
    by_id = {str(t["trackId"]): int(t["index"]) for t in tracks}
    return by_id, by_id


def article_href(track_id: str, by_id: dict[str, int]) -> str:
    idx = by_id.get(track_id)
    if idx is not None:
        return f"content/article.html?index={idx}"
    return f"content/article.html?id={track_id}"


def rewrite_html(html: str, by_id: dict[str, int]) -> str:
    def repl(m: re.Match[str]) -> str:
        prefix, tid, suffix = m.group(1), m.group(2), m.group(3)
        idx = by_id.get(tid)
        href = article_href(tid, by_id)
        suffix = re.sub(r'\s*target="_blank"', "", suffix, flags=re.I)
        suffix = re.sub(r'\s*rel="noopener"', "", suffix, flags=re.I)
        return f"{prefix}{href}{suffix}"

    html = SOUND_HREF.sub(repl, html)
    return rewrite_html_labels(html)


def rewrite_markdown(text: str, by_id: dict[str, int]) -> str:
    def repl(m: re.Match[str]) -> str:
        title, tid = m.group(1), m.group(2)
        idx = by_id.get(tid)
        if idx is not None:
            return f"[{label_index(idx)}{title}](content/article.html?index={idx})"
        return f"[{title}]({article_href(tid, by_id)})"

    text = MD_LINK.sub(repl, text)
    return rewrite_markdown_labels(text)


def patch_data_js() -> int:
    raw = DATA_JS.read_text(encoding="utf-8")
    data = json.loads(raw.split("=", 1)[1].strip().rstrip(";"))
    by_id, _ = build_maps(data["tracks"])
    before = data["systemHtml"]
    after = rewrite_html_labels(rewrite_html(before, by_id))
    data["systemHtml"] = after
    body = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    DATA_JS.write_text(f"window.SHENGSHI_DATA = {body};\n", encoding="utf-8")
    n = len(SOUND_HREF.findall(before))
    left = len(SOUND_HREF.findall(after))
    print(f"data.js: {n} links rewritten, {left} ximalaya links remain")
    return n - left


def patch_markdown() -> int:
    if not SYSTEM_MD.is_file():
        return 0
    raw = DATA_JS.read_text(encoding="utf-8")
    data = json.loads(raw.split("=", 1)[1].strip().rstrip(";"))
    by_id, _ = build_maps(data["tracks"])
    text = SYSTEM_MD.read_text(encoding="utf-8")
    before = len(MD_LINK.findall(text))
    text = rewrite_markdown_labels(rewrite_markdown(text, by_id))
    after = len(MD_LINK.findall(text))
    SYSTEM_MD.write_text(text, encoding="utf-8")
    print(f"investment_system.md: {before - after} links rewritten")
    return before - after


def label_only() -> None:
    """Add 001 · prefixes to existing content/article.html links (no ximalaya rewrite)."""
    raw = DATA_JS.read_text(encoding="utf-8")
    data = json.loads(raw.split("=", 1)[1].strip().rstrip(";"))
    data["systemHtml"] = rewrite_html_labels(data["systemHtml"])
    body = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    DATA_JS.write_text(f"window.SHENGSHI_DATA = {body};\n", encoding="utf-8")
    print("data.js: article link labels updated")

    if SYSTEM_MD.is_file():
        md = rewrite_markdown_labels(SYSTEM_MD.read_text(encoding="utf-8"))
        SYSTEM_MD.write_text(md, encoding="utf-8")
        print("investment_system.md: article link labels updated")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--labels-only":
        label_only()
    else:
        patch_data_js()
        patch_markdown()

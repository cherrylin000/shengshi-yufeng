#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sync index.html surface copy with data-index.js meta after rebuild.

Updates: library-updated date, hero/OG corpus counts, investment_system.md source line.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from data_bundle import load_index  # noqa: E402
from site_meta import CORPUS_COUNT_RE  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
INDEX_HTML = REPO / "index.html"
SYSTEM_MD = REPO / "content" / "investment_system.md"

DATE_PATTERN = re.compile(
    r'(<span class="library-updated">最近更新时间：)\d{4}/\d{1,2}/\d{1,2}(</span>)'
)
OG_DESC_PATTERN = re.compile(
    r'(property="og:description" content="从 )\d+( 份音频文稿中整理投资体系：)'
)
LEAD_PATTERN = re.compile(
    r'(——从 )\d+( 份文稿中整理的可检索知识库。)'
)


def patch_index_html(text: str, ok_count: int) -> tuple[str, list[str]]:
    changes: list[str] = []
    today = date.today()
    label = f"{today.year}/{today.month}/{today.day}"

    new_text, n = DATE_PATTERN.subn(rf"\g<1>{label}\2", text, count=1)
    if n:
        changes.append(f"library-updated -> {label}")

    new_text2, n = OG_DESC_PATTERN.subn(rf"\g<1>{ok_count}\2", new_text, count=1)
    if n:
        changes.append(f"og:description okCount -> {ok_count}")

    new_text3, n = LEAD_PATTERN.subn(rf"\g<1>{ok_count}\2", new_text2, count=1)
    if n:
        changes.append(f"hero lead okCount -> {ok_count}")

    return new_text3, changes


def patch_system_md(text: str, ok_count: int) -> tuple[str, bool]:
    replacement = f"本目录下 {ok_count} 份可用音频"
    new_text, n = CORPUS_COUNT_RE.subn(replacement, text, count=1)
    return new_text, n == 1


def main() -> None:
    data = load_index()
    meta = data.get("meta") or {}
    ok_count = int(meta.get("okCount") or 0)
    track_count = int(meta.get("trackCount") or 0)
    if not track_count:
        raise SystemExit("data-index.js meta.trackCount is missing; run rebuild_data_js.py first")

    html = INDEX_HTML.read_text(encoding="utf-8")
    new_html, html_changes = patch_index_html(html, ok_count)
    if new_html != html:
        INDEX_HTML.write_text(new_html, encoding="utf-8", newline="\n")
    for line in html_changes:
        print(f"index.html: {line}")
    if not html_changes and new_html == html:
        print("index.html: already up to date")

    if SYSTEM_MD.is_file():
        md = SYSTEM_MD.read_text(encoding="utf-8")
        new_md, changed = patch_system_md(md, ok_count)
        if changed and new_md != md:
            SYSTEM_MD.write_text(new_md, encoding="utf-8", newline="\n")
            print(f"investment_system.md: corpus count -> {ok_count}")

    print(
        f"meta sync: trackCount={track_count}, okCount={ok_count}, "
        f"missingCount={meta.get('missingCount')}, charTotal={meta.get('charTotal')}"
    )


if __name__ == "__main__":
    main()

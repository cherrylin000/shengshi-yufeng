#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Set index.html library-updated span to today's date (YYYY/M/D)."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
INDEX_HTML = REPO / "index.html"
PATTERN = re.compile(
    r'(<span class="library-updated">最近更新时间：)\d{4}/\d{1,2}/\d{1,2}(</span>)'
)


def main() -> None:
    today = date.today()
    label = f"{today.year}/{today.month}/{today.day}"
    text = INDEX_HTML.read_text(encoding="utf-8")
    new_text, n = PATTERN.subn(rf"\g<1>{label}\2", text, count=1)
    if n != 1:
        raise SystemExit("library-updated span not found in index.html")
    if new_text == text:
        print(f"Already up to date: {label}")
        return
    INDEX_HTML.write_text(new_text, encoding="utf-8", newline="\n")
    print(f"Updated library-updated -> {label}")


if __name__ == "__main__":
    main()

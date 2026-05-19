#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Add intro + outline from transcript markdown into data.js.

Prefer: python scripts/site/sync_data_from_content.py  (also syncs ASR content + meta)
Or:     python scripts/site/rebuild_data_js.py         (full rebuild)
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DATA_JS = REPO / "data.js"
CONTENT = REPO / "content"
TRANSCRIPTS_ROOT = CONTENT

CHAPTER_LINE = re.compile(r"^- (\d{1,2}:\d{2}(?::\d{2})?)\s+(.+?)\s*$")


def parse_sections(text: str) -> tuple[str | None, list[dict[str, str]]]:
    intro: str | None = None
    outline: list[dict[str, str]] = []
    current: str | None = None
    intro_lines: list[str] = []

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            current = stripped[3:].strip()
            continue
        if current == "AI 简介":
            if stripped and not stripped.startswith(">"):
                intro_lines.append(line.rstrip())
        elif current == "章节速览":
            m = CHAPTER_LINE.match(stripped)
            if m:
                outline.append({"time": m.group(1), "title": m.group(2)})
        elif current and current.startswith("全文文字稿"):
            break

    if intro_lines:
        intro = "\n".join(intro_lines).strip() or None
    return intro, outline


def resolve_md_path(track: dict) -> Path | None:
    rel = track.get("transcriptFile") or ""
    if rel:
        path = TRANSCRIPTS_ROOT / rel.replace("\\", "/")
        if path.is_file():
            return path
    index = track.get("index")
    track_id = track.get("trackId")
    if index is not None and track_id:
        path = TRANSCRIPTS_ROOT / "transcripts" / f"{int(index):03d}_{track_id}.md"
        if path.is_file():
            return path
    return None


def load_data() -> dict:
    raw = DATA_JS.read_text(encoding="utf-8")
    payload = raw.removeprefix("window.SHENGSHI_DATA = ").strip().rstrip(";")
    return json.loads(payload)


def save_data(data: dict) -> None:
    body = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    DATA_JS.write_text(f"window.SHENGSHI_DATA = {body};\n", encoding="utf-8")


def main() -> None:
    data = load_data()
    enriched = 0
    for track in data.get("tracks", []):
        md_path = resolve_md_path(track)
        if not md_path:
            track.pop("intro", None)
            track.pop("outline", None)
            continue
        intro, outline = parse_sections(md_path.read_text(encoding="utf-8"))
        if intro:
            track["intro"] = intro
            enriched += 1
        else:
            track.pop("intro", None)
        if outline:
            track["outline"] = outline
            enriched += 1
        else:
            track.pop("outline", None)
    save_data(data)
    with_outline = sum(1 for t in data["tracks"] if t.get("outline"))
    with_intro = sum(1 for t in data["tracks"] if t.get("intro"))
    print(f"Saved {DATA_JS}")
    print(f"intro: {with_intro}, outline: {with_outline}, tracks: {len(data['tracks'])}")


if __name__ == "__main__":
    main()

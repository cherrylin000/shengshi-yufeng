#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rebuild data.js track fields from content/transcripts/*.md and content/index.csv.

Syncs: intro, outline, content (ASR), charCount, status, publishedAt, playCount.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DATA_JS = REPO / "data.js"
CONTENT = REPO / "content"
INDEX_PATH = CONTENT / "index.csv"
TRACKS_PATH = CONTENT / "tracks.json"
TRANSCRIPTS_DIR = CONTENT / "transcripts"

CHAPTER_LINE = re.compile(r"^- (\d{1,2}:\d{2}(?::\d{2})?)\s+(.+?)\s*$")
META_PUBLISHED = re.compile(r"^- 发布时间：(.+)$")
META_PLAY = re.compile(r"^- 播放量：(\d+)$")
PLACEHOLDER_MARKERS = (
    "暂未抓取",
    "未能提取",
    "无章节速览数据",
    "无可用数据",
    "Show Notes AI 预览",
)


def load_data() -> dict:
    raw = DATA_JS.read_text(encoding="utf-8")
    return json.loads(raw.removeprefix("window.SHENGSHI_DATA = ").strip().rstrip(";"))


def save_data(data: dict) -> None:
    body = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    DATA_JS.write_text(f"window.SHENGSHI_DATA = {body};\n", encoding="utf-8")


def load_index() -> dict[int, dict[str, str]]:
    rows: dict[int, dict[str, str]] = {}
    with INDEX_PATH.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            rows[int(row["trackId"])] = row
    return rows


def load_tracks_json() -> dict[int, dict]:
    tracks = json.loads(TRACKS_PATH.read_text(encoding="utf-8"))
    return {int(t["trackId"]): t for t in tracks}


def resolve_md_path(track: dict) -> Path | None:
    rel = track.get("transcriptFile") or ""
    if rel:
        path = CONTENT / rel.replace("\\", "/")
        if path.is_file():
            return path
    index = track.get("index")
    track_id = track.get("trackId")
    if index is not None and track_id:
        path = TRANSCRIPTS_DIR / f"{int(index):03d}_{track_id}.md"
        if path.is_file():
            return path
    return None


def char_count(text: str) -> int:
    return len(re.sub(r"\s+", "", text))


def parse_markdown(text: str) -> dict:
    intro: str | None = None
    outline: list[dict[str, str]] = []
    content: str | None = None
    published_at: str | None = None
    play_count: int | None = None
    current: str | None = None
    intro_lines: list[str] = []
    content_lines: list[str] = []

    for line in text.splitlines():
        stripped = line.strip()
        m = META_PUBLISHED.match(stripped)
        if m:
            published_at = m.group(1).strip()
            continue
        m = META_PLAY.match(stripped)
        if m:
            play_count = int(m.group(1))
            continue
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
            if stripped.startswith(">"):
                continue
            content_lines.append(line.rstrip())

    if intro_lines:
        intro = "\n".join(intro_lines).strip() or None
    if content_lines:
        body = "\n".join(content_lines).strip()
        if body and not any(m in body for m in PLACEHOLDER_MARKERS):
            content = body
    return {
        "intro": intro,
        "outline": outline or None,
        "content": content,
        "publishedAt": published_at,
        "playCount": play_count,
    }


def apply_parsed(track: dict, parsed: dict, index_row: dict[str, str] | None, tj: dict | None) -> None:
    if parsed.get("intro"):
        track["intro"] = parsed["intro"]
    else:
        track.pop("intro", None)

    outline = parsed.get("outline") or []
    if outline:
        track["outline"] = outline
    else:
        track.pop("outline", None)

    content = parsed.get("content")
    status = (index_row or {}).get("status") or track.get("status") or "unavailable"
    if content:
        track["content"] = content
        track["charCount"] = char_count(content)
        track["status"] = "ok"
        track["segments"] = max(1, content.count("\n\n") + 1)
        track.pop("error", None)
    else:
        track.pop("content", None)
        track["status"] = status
        if index_row:
            track["charCount"] = int(index_row.get("charCount") or 0)
            track["segments"] = int(index_row.get("segments") or 0)
            err = index_row.get("error") or ""
            if err:
                track["error"] = err
            else:
                track.pop("error", None)

    published = parsed.get("publishedAt")
    if not published and tj:
        published = tj.get("publishedAt")
    if published:
        track["publishedAt"] = published
    elif "publishedAt" in track:
        del track["publishedAt"]

    play = parsed.get("playCount")
    if play is None and tj:
        play = tj.get("playCount")
    if play is not None:
        track["playCount"] = int(play)
    elif "playCount" in track:
        del track["playCount"]


def main() -> None:
    data = load_data()
    index_by_id = load_index()
    tracks_json = load_tracks_json()
    updated_content = 0
    updated_intro = 0
    updated_outline = 0

    for track in data.get("tracks", []):
        tid = int(track["trackId"])
        md_path = resolve_md_path(track)
        if not md_path:
            continue
        parsed = parse_markdown(md_path.read_text(encoding="utf-8"))
        before = track.get("content")
        apply_parsed(track, parsed, index_by_id.get(tid), tracks_json.get(tid))
        if track.get("content") and track.get("content") != before:
            updated_content += 1
        if track.get("intro"):
            updated_intro += 1
        if track.get("outline"):
            updated_outline += 1

    save_data(data)
    ok = sum(1 for t in data["tracks"] if t.get("status") == "ok")
    with_pub = sum(1 for t in data["tracks"] if t.get("publishedAt"))
    with_play = sum(1 for t in data["tracks"] if t.get("playCount") is not None)
    print(f"Saved {DATA_JS}")
    print(
        f"tracks: {len(data['tracks'])}, ok: {ok}, intro: {updated_intro}, "
        f"outline: {updated_outline}, content updated: {updated_content}, "
        f"publishedAt: {with_pub}, playCount: {with_play}"
    )


if __name__ == "__main__":
    main()

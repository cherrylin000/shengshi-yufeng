#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rebuild data-index.js + content/articles from transcripts.

Content priority for each track:
  1) content/polished/{index}_{trackId}.md（润色结构化文稿）
  2) content/transcripts/*.md（默认 ASR / 原文文稿）
  3) 空（无正文）

Also attaches SmartArt diagram URLs when polished diagrams exist.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CONTENT = REPO / "content"
INDEX_PATH = CONTENT / "index.csv"
TRACKS_PATH = CONTENT / "tracks.json"
TRANSCRIPTS_DIR = CONTENT / "transcripts"
POLISHED_DIR = CONTENT / "polished"
DIAGRAMS_DIR = CONTENT / "diagrams"

CHAPTER_LINE = re.compile(r"^- (\d{1,2}:\d{2}(?::\d{2})?)\s+(.+?)\s*$")
CHAPTER_NUM_LINE = re.compile(
    r"^\d+\.\s+\*\*(\d{1,2}:\d{2}(?::\d{2})?)\*\*\s+(.+?)\s*$"
)
META_PUBLISHED = re.compile(r"^- 发布时间：(.+)$")
META_PLAY = re.compile(r"^- 播放量：(\d+)$")
MD_IMAGE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
PLACEHOLDER_MARKERS = (
    "暂未抓取",
    "未能提取",
    "无章节速览数据",
    "无可用数据",
    "Show Notes AI 预览",
)


from data_bundle import load_data, save_data  # noqa: E402
from site_meta import recompute_meta  # noqa: E402


def load_index_rows() -> list[dict[str, str]]:
    with INDEX_PATH.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def load_index() -> dict[int, dict[str, str]]:
    rows: dict[int, dict[str, str]] = {}
    for row in load_index_rows():
        rows[int(row["trackId"])] = row
    return rows


def new_track_from_index(row: dict[str, str], tj: dict | None) -> dict:
    tid = int(row["trackId"])
    track: dict = {
        "index": int(row["index"]),
        "trackId": tid,
        "title": row.get("title") or (tj or {}).get("title") or "",
        "duration": int(row.get("duration") or (tj or {}).get("duration") or 0),
        "status": row.get("status") or "unavailable",
        "charCount": int(row.get("charCount") or 0),
        "segments": int(row.get("segments") or 0),
    }
    rel = row.get("transcriptFile") or ""
    if rel:
        track["transcriptFile"] = rel
    if row.get("publishedAt"):
        track["publishedAt"] = row["publishedAt"]
    elif tj and tj.get("publishedAt"):
        track["publishedAt"] = tj["publishedAt"]
    if row.get("playCount"):
        track["playCount"] = int(row["playCount"])
    elif tj and tj.get("playCount") is not None:
        track["playCount"] = int(tj["playCount"])
    err = row.get("error") or ""
    if err:
        track["error"] = err
    return track


def merge_tracks_from_index(data: dict, index_rows: list[dict[str, str]], tracks_json: dict[int, dict]) -> int:
    """Align data-index tracks with index.csv (add new rows, drop removed, refresh index order)."""
    existing = {int(t["trackId"]): t for t in data.get("tracks", [])}
    merged: list[dict] = []
    added = 0
    for row in sorted(index_rows, key=lambda r: int(r["index"])):
        tid = int(row["trackId"])
        track = existing.get(tid)
        if track is None:
            track = new_track_from_index(row, tracks_json.get(tid))
            added += 1
        else:
            track["index"] = int(row["index"])
            if row.get("title"):
                track["title"] = row["title"]
            if row.get("duration"):
                track["duration"] = int(row["duration"])
        merged.append(track)
    data["tracks"] = merged
    return added


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


def resolve_polished_path(track: dict) -> Path | None:
    index = track.get("index")
    track_id = track.get("trackId")
    if index is None or not track_id:
        return None
    path = POLISHED_DIR / f"{int(index):03d}_{int(track_id)}.md"
    return path if path.is_file() else None


def discover_diagrams(track: dict, polished_text: str | None = None) -> list[dict[str, str]]:
    """Return diagram payloads with web-relative src under content/."""
    diagrams: list[dict[str, str]] = []
    seen: set[str] = set()

    def add(src: str, title: str = "") -> None:
        src = src.replace("\\", "/")
        if src.startswith("../"):
            src = src[3:]
        if src.startswith("./"):
            src = src[2:]
        if src.startswith("diagrams/"):
            web_src = src
            disk = CONTENT / src
        elif "/" not in src:
            web_src = f"diagrams/{src}"
            disk = DIAGRAMS_DIR / src
        else:
            web_src = src
            disk = CONTENT / src
        if not disk.is_file() or web_src in seen:
            return
        seen.add(web_src)
        kind = "flowchart" if "flow" in disk.name else ("mindmap" if "mind" in disk.name else "diagram")
        diagrams.append(
            {
                "id": kind,
                "src": web_src,
                "title": title or ("章节流程图" if kind == "flowchart" else "章节脑图" if kind == "mindmap" else disk.stem),
            }
        )

    if polished_text:
        for m in MD_IMAGE.finditer(polished_text):
            add(m.group(2).strip(), m.group(1).strip())

    index = track.get("index")
    track_id = track.get("trackId")
    if index is not None and track_id:
        stem = f"{int(index):03d}_{int(track_id)}"
        for name, title in (
            (f"{stem}_flowchart.svg", "章节流程图"),
            (f"{stem}_mindmap.svg", "章节脑图"),
        ):
            add(f"diagrams/{name}", title)
    return diagrams


def char_count(text: str) -> int:
    return len(re.sub(r"\s+", "", text))


def parse_markdown(text: str) -> dict:
    """Parse default transcript markdown (AI 简介 / 章节速览 / 全文文字稿)."""
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
        if current in ("AI 简介", "AI 简介（润色）"):
            if stripped and not stripped.startswith(">"):
                intro_lines.append(line.rstrip())
        elif current in ("章节速览", "章节目录"):
            m = CHAPTER_LINE.match(stripped) or CHAPTER_NUM_LINE.match(stripped)
            if m:
                outline.append({"time": m.group(1), "title": m.group(2)})
        elif current and (
            current.startswith("全文文字稿")
            or current.startswith("整理后正文")
            or current.startswith("要点提纲")
        ):
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


def parse_polished_markdown(text: str) -> dict:
    """Parse polished markdown; keep structured ### headings inside content."""
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
        if current in ("AI 简介", "AI 简介（润色）"):
            if stripped and not stripped.startswith(">"):
                intro_lines.append(line.rstrip())
        elif current in ("章节目录", "章节速览"):
            m = CHAPTER_NUM_LINE.match(stripped) or CHAPTER_LINE.match(stripped)
            if m:
                outline.append({"time": m.group(1), "title": m.group(2)})
        elif current and (
            current.startswith("整理后正文")
            or current.startswith("全文文字稿")
            or current.startswith("要点提纲")
        ):
            if stripped.startswith(">"):
                continue
            content_lines.append(line.rstrip())
        # skip 结构图（SmartArt） body; diagrams discovered separately

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


def apply_parsed(
    track: dict,
    parsed: dict,
    index_row: dict[str, str] | None,
    tj: dict | None,
    *,
    content_source: str | None = None,
    diagrams: list[dict[str, str]] | None = None,
) -> None:
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
        if content_source:
            track["contentSource"] = content_source
        else:
            track.pop("contentSource", None)
    else:
        track.pop("content", None)
        track.pop("contentSource", None)
        track["status"] = status
        if index_row:
            track["charCount"] = int(index_row.get("charCount") or 0)
            track["segments"] = int(index_row.get("segments") or 0)
            err = index_row.get("error") or ""
            if err:
                track["error"] = err
            else:
                track.pop("error", None)

    if diagrams:
        track["diagrams"] = diagrams
    else:
        track.pop("diagrams", None)

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


def load_track_content(track: dict, index_row: dict[str, str] | None) -> tuple[dict, str | None, list[dict[str, str]]]:
    """
    Prefer polished structured transcript, else default transcript, else empty.
    Returns (parsed, content_source, diagrams).
    """
    polished = resolve_polished_path(track)
    if polished:
        text = polished.read_text(encoding="utf-8")
        parsed = parse_polished_markdown(text)
        diagrams = discover_diagrams(track, text)
        if parsed.get("content") or diagrams:
            # If polished has outline/intro/diagrams but empty body, still prefer it
            # and only fall back body from raw when needed.
            if not parsed.get("content"):
                raw_path = resolve_md_path(track)
                if not raw_path and index_row and index_row.get("transcriptFile"):
                    raw_path = CONTENT / index_row["transcriptFile"].replace("\\", "/")
                if raw_path and raw_path.is_file():
                    raw = parse_markdown(raw_path.read_text(encoding="utf-8"))
                    if raw.get("content"):
                        parsed["content"] = raw["content"]
                    if not parsed.get("intro") and raw.get("intro"):
                        parsed["intro"] = raw["intro"]
                    if not parsed.get("outline") and raw.get("outline"):
                        parsed["outline"] = raw["outline"]
                    if not parsed.get("publishedAt") and raw.get("publishedAt"):
                        parsed["publishedAt"] = raw["publishedAt"]
                    if parsed.get("playCount") is None and raw.get("playCount") is not None:
                        parsed["playCount"] = raw["playCount"]
            return parsed, "polished", diagrams

    raw_path = resolve_md_path(track)
    if not raw_path and index_row and index_row.get("transcriptFile"):
        raw_path = CONTENT / index_row["transcriptFile"].replace("\\", "/")
    if raw_path and raw_path.is_file():
        parsed = parse_markdown(raw_path.read_text(encoding="utf-8"))
        return parsed, ("raw" if parsed.get("content") else None), []

    return {
        "intro": None,
        "outline": None,
        "content": None,
        "publishedAt": None,
        "playCount": None,
    }, None, []


def main() -> None:
    data = load_data()
    index_rows = load_index_rows()
    index_by_id = {int(row["trackId"]): row for row in index_rows}
    tracks_json = load_tracks_json()
    added = merge_tracks_from_index(data, index_rows, tracks_json)
    updated_content = 0
    updated_intro = 0
    updated_outline = 0
    polished_count = 0

    for track in data.get("tracks", []):
        tid = int(track["trackId"])
        index_row = index_by_id.get(tid)
        parsed, source, diagrams = load_track_content(track, index_row)
        before = track.get("content")
        apply_parsed(
            track,
            parsed,
            index_row,
            tracks_json.get(tid),
            content_source=source,
            diagrams=diagrams,
        )
        if track.get("content") and track.get("content") != before:
            updated_content += 1
        if track.get("intro"):
            updated_intro += 1
        if track.get("outline"):
            updated_outline += 1
        if track.get("contentSource") == "polished":
            polished_count += 1

    stats = recompute_meta(data)
    save_data(data)
    with_pub = sum(1 for t in data["tracks"] if t.get("publishedAt"))
    with_play = sum(1 for t in data["tracks"] if t.get("playCount") is not None)
    with_diagrams = sum(1 for t in data["tracks"] if t.get("diagrams"))
    print("Saved data-index.js + content/articles/")
    print(
        f"tracks: {stats['trackCount']} (+{added} new), ok: {stats['okCount']}, "
        f"missing: {stats['missingCount']}, chars: {stats['charTotal']}, "
        f"intro: {updated_intro}, outline: {updated_outline}, content updated: {updated_content}, "
        f"polished: {polished_count}, diagrams: {with_diagrams}, "
        f"publishedAt: {with_pub}, playCount: {with_play}"
    )


if __name__ == "__main__":
    main()

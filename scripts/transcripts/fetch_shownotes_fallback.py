#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fetch Ximalaya Show Notes (AI preview) for tracks missing aiDocUrl."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CONTENT = REPO / "content"
TRACKS_PATH = CONTENT / "tracks.json"
ERRORS_PATH = CONTENT / "errors.json"
INDEX_PATH = CONTENT / "index.csv"
TRANSCRIPTS_DIR = CONTENT / "transcripts"
ERRORS_SHOWNOTES_PATH = CONTENT / "errors_shownotes.json"
SHOWNOTES_API = "https://m.ximalaya.com/anchor-works-web/shownotes/page?trackId={track_id}"

ASR_PLACEHOLDER = (
    "> 本条音频未返回 aiDocUrl，全文 ASR 暂未抓取。"
    "以下章节速览来自喜马拉雅 Show Notes AI 预览，仅供检索与粗对齐，不可当作口播逐字稿。"
)

EMPTY_CHAPTER_NOTE = "- （未提取到章节速览）"

EMPTY_ASR_PLACEHOLDER = (
    "> 本条音频未返回 aiDocUrl，且喜马拉雅 Show Notes 无可用数据，"
    "未能提取 AI 简介、章节速览或全文 ASR 文稿。"
)


def format_duration(seconds: int) -> str:
    m, s = divmod(max(0, int(seconds)), 60)
    return f"{m}:{s:02d}"


def ms_to_timestamp(ms: int) -> str:
    total = max(0, int(ms)) // 1000
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def normalize_chapter_time(ts: str) -> str:
    """Match existing transcripts: MM:SS (collapse leading hours into minutes)."""
    ts = ts.strip()
    parts = ts.split(":")
    if len(parts) == 3:
        h, m, s = (int(p) for p in parts)
        return f"{h * 60 + m:02d}:{s:02d}"
    if len(parts) == 2:
        return f"{int(parts[0]):02d}:{int(parts[1]):02d}"
    return ts


def fetch_shownotes(track_id: int, retries: int = 3, cookie: str | None = None) -> dict:
    url = SHOWNOTES_API.format(track_id=track_id)
    cookie = cookie or os.environ.get("XIMALAYA_COOKIE", "").strip() or None
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
        ),
        "Accept": "application/json",
    }
    if cookie:
        headers["Cookie"] = cookie
        headers["Referer"] = f"https://www.ximalaya.com/sound/{track_id}"
    req = urllib.request.Request(url, headers=headers)
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError) as e:
            last_err = e
            if attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
    raise last_err  # type: ignore[misc]


def parse_shownotes_payload(payload: dict) -> tuple[str | None, list[tuple[str, str]]]:
    if payload.get("success") is False:
        raise ValueError(payload.get("msg") or "API returned success=false")
    if payload.get("ret") not in (0, None) and not payload.get("success"):
        raise ValueError(payload.get("msg") or payload.get("error") or "API error")

    data = payload.get("data") or {}
    ai_intro = data.get("aiIntro") or data.get("trackRichIntro")
    if ai_intro is not None and not str(ai_intro).strip():
        ai_intro = None

    notes = data.get("shownotes") or data.get("showNotes") or []
    chapters: list[tuple[str, str]] = []
    for item in sorted(notes, key=lambda x: x.get("startAt") or 0):
        start_ms = item.get("startAt")
        if start_ms is None:
            continue
        title = (item.get("summary") or item.get("title") or "").strip()
        if not title:
            continue
        ts = normalize_chapter_time(ms_to_timestamp(int(start_ms)))
        chapters.append((ts, title))
    return ai_intro, chapters


def load_tracks() -> dict[int, dict]:
    tracks = json.loads(TRACKS_PATH.read_text(encoding="utf-8"))
    return {int(t["trackId"]): t for t in tracks}


def char_count_preview(text: str) -> int:
    """Count non-whitespace chars in intro + chapter lines only."""
    parts: list[str] = []
    in_intro = False
    in_chapters = False
    for line in text.splitlines():
        if line.strip() == "## AI 简介":
            in_intro = True
            in_chapters = False
            continue
        if line.strip() == "## 章节速览":
            in_chapters = True
            in_intro = False
            continue
        if line.startswith("## "):
            in_intro = in_chapters = False
            continue
        if in_intro or in_chapters:
            if line.startswith("- "):
                parts.append(line[2:])
            elif line.strip() and in_intro:
                parts.append(line)
    return len(re.sub(r"\s+", "", "".join(parts)))


def meta_extra_lines(track: dict) -> list[str]:
    lines: list[str] = []
    published = track.get("publishedAt")
    if published:
        lines.append(f"- 发布时间：{published}")
    play_count = track.get("playCount")
    if play_count is not None:
        lines.append(f"- 播放量：{play_count}")
    return lines


def build_markdown(track: dict, ai_intro: str | None, chapters: list[tuple[str, str]]) -> str:
    track_id = int(track["trackId"])
    index = int(track["index"])
    title = track.get("title") or f"track {track_id}"
    duration = int(track.get("duration") or 0)
    album = track.get("albumTitle") or "盛世裕丰"
    anchor = track.get("anchorName") or "盛世裕丰财富之道"
    url_path = track.get("url") or f"/sound/{track_id}"
    link = f"https://www.ximalaya.com{url_path}"

    lines = [
        f"# {title}",
        "",
        f"- 音频 ID：{track_id}",
        f"- 序号：{index}",
        f"- 专辑：{album}",
        f"- 主播：{anchor}",
        f"- 时长：{format_duration(duration)}",
        f"- 原链接：{link}",
        *meta_extra_lines(track),
        "",
    ]

    if ai_intro:
        lines.extend(["## AI 简介", "", str(ai_intro).strip(), ""])

    lines.extend(["## 章节速览", ""])
    if chapters:
        for ts, chap_title in chapters:
            lines.append(f"- {ts} {chap_title}")
    else:
        lines.append("- （无章节速览数据）")
    lines.extend(["", "## 全文文字稿（ASR）", "", ASR_PLACEHOLDER, ""])
    return "\n".join(lines)


def build_empty_markdown(track: dict) -> str:
    """Placeholder when neither aiDocUrl nor Show Notes are available."""
    track_id = int(track["trackId"])
    index = int(track["index"])
    title = track.get("title") or f"track {track_id}"
    duration = int(track.get("duration") or 0)
    album = track.get("albumTitle") or "盛世裕丰"
    anchor = track.get("anchorName") or "盛世裕丰财富之道"
    url_path = track.get("url") or f"/sound/{track_id}"
    link = f"https://www.ximalaya.com{url_path}"

    lines = [
        f"# {title}",
        "",
        f"- 音频 ID：{track_id}",
        f"- 序号：{index}",
        f"- 专辑：{album}",
        f"- 主播：{anchor}",
        f"- 时长：{format_duration(duration)}",
        f"- 原链接：{link}",
        *meta_extra_lines(track),
        "",
        "## 章节速览",
        "",
        EMPTY_CHAPTER_NOTE,
        "",
        "## 全文文字稿（ASR）",
        "",
        EMPTY_ASR_PLACEHOLDER,
        "",
    ]
    return "\n".join(lines)


def write_empty_stub(
    track_id: int,
    tracks_by_id: dict[int, dict],
    *,
    dry_run: bool = False,
    resume: bool = False,
) -> tuple[bool, str]:
    track = tracks_by_id.get(track_id)
    if not track:
        return False, "not in tracks.json"

    out = TRANSCRIPTS_DIR / f"{int(track['index']):03d}_{track_id}.md"
    if resume and out.is_file():
        text = out.read_text(encoding="utf-8")
        if EMPTY_ASR_PLACEHOLDER[:20] in text or "未能提取" in text:
            return True, f"skipped (exists) {out.name}"

    md = build_empty_markdown(track)
    if dry_run:
        return True, "dry-run empty stub"
    out.write_text(md, encoding="utf-8", newline="\n")
    return True, out.name


def update_index_csv(updates: dict[int, dict]) -> None:
    rows: list[dict[str, str]] = []
    with INDEX_PATH.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        for row in reader:
            tid = int(row["trackId"])
            if tid in updates:
                u = updates[tid]
                row["status"] = u["status"]
                row["charCount"] = str(u["charCount"])
                row["segments"] = str(u["segments"])
                row["transcriptFile"] = u["transcriptFile"]
                row["error"] = u.get("error", "")
            rows.append(row)
    with INDEX_PATH.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def process_track(
    track_id: int,
    tracks_by_id: dict[int, dict],
    *,
    dry_run: bool = False,
    resume: bool = False,
) -> tuple[bool, str]:
    track = tracks_by_id.get(track_id)
    if not track:
        return False, "not in tracks.json"

    out = TRANSCRIPTS_DIR / f"{int(track['index']):03d}_{track_id}.md"
    if resume and out.is_file():
        text = out.read_text(encoding="utf-8")
        if "## 章节速览" in text and "Show Notes AI 预览" in text:
            return True, f"skipped (exists) {out.name}"

    try:
        payload = fetch_shownotes(track_id)
        ai_intro, chapters = parse_shownotes_payload(payload)
    except (urllib.error.URLError, ValueError, json.JSONDecodeError, OSError) as e:
        return False, str(e)

    if not chapters and not ai_intro:
        return False, "no shownotes or aiIntro"

    md = build_markdown(track, ai_intro, chapters)
    if dry_run:
        return True, f"dry-run chapters={len(chapters)} ai_intro={'yes' if ai_intro else 'no'}"

    out.write_text(md, encoding="utf-8", newline="\n")
    return True, out.name


def main() -> None:
    ap = argparse.ArgumentParser(description="Fetch Show Notes fallback for failed tracks.")
    ap.add_argument("--track-id", type=int, default=0)
    ap.add_argument("--errors", action="store_true", help="Process all tracks in errors.json")
    ap.add_argument(
        "--write-empty",
        action="store_true",
        help="Write placeholder md for tracks in errors_shownotes.json",
    )
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--resume", action="store_true", help="Skip existing preview transcripts")
    ap.add_argument("--delay", type=float, default=2.0)
    ap.add_argument("--update-index", action="store_true", help="Update index.csv and errors.json")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    tracks_by_id = load_tracks()
    if args.track_id:
        ids = [args.track_id]
        write_empty = False
    elif args.write_empty:
        src = ERRORS_SHOWNOTES_PATH if ERRORS_SHOWNOTES_PATH.is_file() else ERRORS_PATH
        err = json.loads(src.read_text(encoding="utf-8"))
        ids = [int(e["trackId"]) for e in err]
        write_empty = True
    elif args.errors:
        err = json.loads(ERRORS_PATH.read_text(encoding="utf-8"))
        ids = [int(e["trackId"]) for e in err]
        write_empty = False
    else:
        ap.error("Specify --track-id, --errors, or --write-empty")

    if args.limit > 0:
        ids = ids[: args.limit]

    ok_ids: list[int] = []
    fail_list: list[dict] = []
    index_updates: dict[int, dict] = {}

    for i, track_id in enumerate(ids):
        if write_empty:
            success, msg = write_empty_stub(
                track_id, tracks_by_id, dry_run=args.dry_run, resume=args.resume
            )
        else:
            success, msg = process_track(
                track_id, tracks_by_id, dry_run=args.dry_run, resume=args.resume
            )
        track = tracks_by_id[track_id]
        if success and not args.dry_run:
            out = TRANSCRIPTS_DIR / f"{int(track['index']):03d}_{track_id}.md"
            if out.is_file():
                md = out.read_text(encoding="utf-8")
                if write_empty or EMPTY_ASR_PLACEHOLDER[:20] in md:
                    index_updates[track_id] = {
                        "status": "unavailable",
                        "charCount": 0,
                        "segments": 0,
                        "transcriptFile": f"transcripts/{out.name}",
                        "error": "",
                    }
                else:
                    after = md.split("## 章节速览", 1)[-1].split("## ", 1)[0]
                    segs = sum(1 for ln in after.splitlines() if ln.startswith("- "))
                    index_updates[track_id] = {
                        "status": "preview",
                        "charCount": char_count_preview(md),
                        "segments": segs,
                        "transcriptFile": f"transcripts/{out.name}",
                        "error": "",
                    }
            ok_ids.append(track_id)
            print(f"[OK] {track_id} -> {msg}")
        elif success:
            print(f"[OK] {track_id} {msg}")
        else:
            fail_list.append(
                {
                    "trackId": track_id,
                    "index": track["index"],
                    "title": track.get("title", ""),
                    "error": msg,
                }
            )
            print(f"[FAIL] {track_id}: {msg}")

        if (
            not args.dry_run
            and not write_empty
            and args.delay
            and i < len(ids) - 1
        ):
            time.sleep(args.delay)

    if args.update_index and not args.dry_run:
        if index_updates:
            update_index_csv(index_updates)
            print(f"Updated index.csv for {len(index_updates)} tracks")

        if (args.errors or args.write_empty) and ERRORS_PATH.is_file():
            remaining = [
                e
                for e in json.loads(ERRORS_PATH.read_text(encoding="utf-8"))
                if int(e["trackId"]) not in ok_ids
            ]
            ERRORS_PATH.write_text(
                json.dumps(remaining, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            print(f"errors.json: {len(ok_ids)} removed, {len(remaining)} remaining")

        if args.write_empty and not args.dry_run:
            ERRORS_SHOWNOTES_PATH.write_text("[]\n", encoding="utf-8")
            print("Cleared errors_shownotes.json (stubs written)")

        if fail_list and not args.write_empty:
            ERRORS_SHOWNOTES_PATH.write_text(
                json.dumps(fail_list, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            print(f"Wrote {len(fail_list)} failures to errors_shownotes.json")

    print(f"Done: ok={len(ok_ids)} fail={len(fail_list)} dry_run={args.dry_run}")


if __name__ == "__main__":
    main()

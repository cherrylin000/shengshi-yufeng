#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sync Ximalaya album track list into tracks.json + index.csv, and fetch markdown
transcripts for newly discovered tracks.

Transcript fallback (always writes .md):
  1. Mobile「原文文稿」via aiDoc/page (requires XIMALAYA_COOKIE)
  2. Full ASR via Show Notes aiDocUrl when available
  3. Show Notes preview (AI intro + chapter outline)
  4. Empty placeholder stub
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
import urllib.error
import urllib.request
from copy import deepcopy
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CONTENT = REPO / "content"
TRACKS_PATH = CONTENT / "tracks.json"
INDEX_PATH = CONTENT / "index.csv"
TRANSCRIPTS_DIR = CONTENT / "transcripts"

DEFAULT_ALBUM_ID = 41054149
ALBUM_PAGE_API = (
    "http://mobwsa.ximalaya.com/mobile/playlist/album/page"
    "?albumId={album_id}&pageId={page_id}"
)
MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)

INDEX_FIELDS = [
    "index",
    "trackId",
    "title",
    "duration",
    "status",
    "charCount",
    "segments",
    "transcriptFile",
    "error",
    "publishedAt",
    "playCount",
]

PLACEHOLDER_MARKERS = (
    "暂未抓取",
    "未能提取",
    "无章节速览数据",
    "无可用数据",
    "Show Notes AI 预览",
    "未提取到章节速览",
)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_shownotes_fallback import (  # noqa: E402
    build_empty_markdown,
    build_markdown,
    char_count_preview,
    fetch_shownotes,
    format_duration,
    meta_extra_lines,
    parse_shownotes_payload,
)
from fetch_aidoc import fetch_aidoc_text, get_cookie  # noqa: E402


def char_count(text: str) -> int:
    return len(re.sub(r"\s+", "", text))


def http_json(url: str, *, retries: int = 5, timeout: float = 60) -> dict:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": MOBILE_UA,
            "Accept": "application/json",
            "Referer": "https://m.ximalaya.com/",
        },
    )
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                time.sleep(3 * (attempt + 1))
                continue
            raise
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            last_err = e
            if attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
    raise last_err  # type: ignore[misc]


def fetch_album_page(album_id: int, page_id: int, *, timeout: float = 60) -> dict:
    url = ALBUM_PAGE_API.format(album_id=album_id, page_id=page_id)
    payload = http_json(url, timeout=timeout)
    if payload.get("ret") not in (0, None):
        raise ValueError(payload.get("msg") or "album API error")
    return payload


def fetch_all_api_tracks(album_id: int, *, timeout: float = 60) -> list[dict]:
    first = fetch_album_page(album_id, 1, timeout=timeout)
    max_page = int(first.get("maxPageId") or 1)
    items: list[dict] = list(first.get("list") or [])
    for page_id in range(2, max_page + 1):
        payload = fetch_album_page(album_id, page_id, timeout=timeout)
        items.extend(payload.get("list") or [])
        time.sleep(0.3)
    by_id: dict[int, dict] = {}
    for item in items:
        by_id[int(item["trackId"])] = item
    return [by_id[k] for k in sorted(by_id)]


def format_published_at(ms: int | None) -> str | None:
    if ms is None:
        return None
    return datetime.fromtimestamp(int(ms) / 1000).strftime("%Y-%m-%d %H:%M:%S")


def load_local_tracks() -> list[dict]:
    if not TRACKS_PATH.is_file():
        return []
    return json.loads(TRACKS_PATH.read_text(encoding="utf-8"))


def track_template(local: list[dict]) -> dict:
    if local:
        return deepcopy(local[0])
    return {
        "isPaid": False,
        "tag": 0,
        "showLikeBtn": True,
        "isLike": False,
        "showShareBtn": True,
        "showCommentBtn": True,
        "showForwardBtn": True,
        "isVideo": False,
        "isVipFirst": False,
        "breakSecond": 0,
        "albumId": DEFAULT_ALBUM_ID,
        "albumTitle": "盛世裕丰",
        "albumCoverPath": "group85/M0A/0D/3C/wKg5JV8-2tPR2aQkAAExxu-H6I0190.jpg",
        "anchorId": 41485134,
        "anchorName": "盛世裕丰财富之道",
        "ximiVipFreeType": 0,
        "joinXimi": False,
    }


def map_api_item(item: dict, index: int, template: dict) -> dict:
    track_id = int(item["trackId"])
    duration = int(item.get("duration") or 0)
    published = format_published_at(item.get("createdAt"))
    title = item.get("title") or f"track {track_id}"
    create_date_format = published[:7] if published else (item.get("createDateFormat") or "")

    track = {
        "index": index,
        "trackId": track_id,
        "isPaid": bool(item.get("isPaid")),
        "tag": int(template.get("tag") or 0),
        "title": title,
        "playCount": int(item.get("playtimes") or 0),
        "showLikeBtn": template.get("showLikeBtn", True),
        "isLike": template.get("isLike", False),
        "showShareBtn": template.get("showShareBtn", True),
        "showCommentBtn": template.get("showCommentBtn", True),
        "showForwardBtn": template.get("showForwardBtn", True),
        "createDateFormat": create_date_format,
        "url": f"/sound/{track_id}",
        "duration": duration,
        "isVideo": bool(item.get("isVideo")),
        "isVipFirst": template.get("isVipFirst", False),
        "breakSecond": template.get("breakSecond", 0),
        "length": duration,
        "albumId": int(item.get("albumId") or template.get("albumId") or DEFAULT_ALBUM_ID),
        "albumTitle": item.get("albumTitle") or template.get("albumTitle") or "盛世裕丰",
        "albumCoverPath": template.get("albumCoverPath", ""),
        "anchorId": int(item.get("uid") or template.get("anchorId") or 0),
        "anchorName": template.get("anchorName") or "盛世裕丰财富之道",
        "ximiVipFreeType": template.get("ximiVipFreeType", 0),
        "joinXimi": template.get("joinXimi", False),
    }
    if published:
        track["publishedAt"] = published
    return track


def merge_tracks(
    local: list[dict],
    api_items: list[dict],
    *,
    reindex_from_api: bool = False,
) -> tuple[list[dict], list[int], list[int]]:
    """Return merged tracks, new track IDs, updated track IDs."""
    template = track_template(local)
    local_by_id = {int(t["trackId"]): t for t in local}
    max_index = max((int(t["index"]) for t in local), default=0)

    new_ids: list[int] = []
    updated_ids: list[int] = []

    if reindex_from_api:
        sorted_api = sorted(api_items, key=lambda x: int(x.get("orderNo") or 0))
        merged = []
        for i, item in enumerate(sorted_api, start=1):
            tid = int(item["trackId"])
            prev = local_by_id.get(tid, {})
            track = map_api_item(item, i, template)
            if prev.get("publishedAt") and not track.get("publishedAt"):
                track["publishedAt"] = prev["publishedAt"]
            merged.append(track)
            if tid not in local_by_id:
                new_ids.append(tid)
            elif prev.get("title") != track.get("title") or prev.get("playCount") != track.get("playCount"):
                updated_ids.append(tid)
        merged.sort(key=lambda t: int(t["index"]))
        return merged, new_ids, updated_ids

    merged_by_id: dict[int, dict] = {}
    for tid, old in local_by_id.items():
        merged_by_id[tid] = deepcopy(old)

    for item in api_items:
        tid = int(item["trackId"])
        if tid in merged_by_id:
            old = merged_by_id[tid]
            fresh = map_api_item(item, int(old["index"]), template)
            for key in ("title", "duration", "length", "playCount", "url", "isPaid", "isVideo", "albumTitle"):
                old[key] = fresh[key]
            if fresh.get("publishedAt"):
                old["publishedAt"] = fresh["publishedAt"]
            if old != local_by_id[tid]:
                updated_ids.append(tid)
        else:
            max_index += 1
            merged_by_id[tid] = map_api_item(item, max_index, template)
            new_ids.append(tid)

    merged = sorted(merged_by_id.values(), key=lambda t: int(t["index"]))
    return merged, new_ids, updated_ids


def transcript_path(track: dict) -> Path:
    return TRANSCRIPTS_DIR / f"{int(track['index']):03d}_{int(track['trackId'])}.md"


def build_markdown_with_asr(
    track: dict,
    ai_intro: str | None,
    chapters: list[tuple[str, str]],
    asr_body: str,
) -> str:
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
    lines.extend(["", "## 全文文字稿（ASR）", "", asr_body.strip(), ""])
    return "\n".join(lines)


def fetch_ai_document(url: str) -> str | None:
    req = urllib.request.Request(url, headers={"User-Agent": MOBILE_UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode("utf-8", errors="replace").strip()
    if not raw:
        return None
    if raw.startswith("{"):
        data = json.loads(raw)
        for key in ("content", "text", "body", "asrText", "docContent", "fullText"):
            val = data.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
        nested = data.get("data")
        if isinstance(nested, dict):
            for key in ("content", "text", "body", "asrText", "docContent", "fullText"):
                val = nested.get(key)
                if isinstance(val, str) and val.strip():
                    return val.strip()
        if isinstance(nested, str) and nested.strip():
            return nested.strip()
        return None
    return raw


def count_chapter_segments(md: str) -> int:
    if "## 章节速览" not in md:
        return 0
    after = md.split("## 章节速览", 1)[-1].split("## ", 1)[0]
    return sum(1 for ln in after.splitlines() if ln.startswith("- ") and "未提取" not in ln)


def analyze_md(md: str) -> tuple[str, int, int]:
    """Return status, charCount, segments from existing markdown."""
    content_lines: list[str] = []
    in_asr = False
    for line in md.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            in_asr = stripped[3:].strip().startswith("全文文字稿")
            continue
        if in_asr:
            if stripped.startswith(">"):
                continue
            content_lines.append(line.rstrip())

    body = "\n".join(content_lines).strip()
    if body and not any(m in body for m in PLACEHOLDER_MARKERS):
        segments = max(1, body.count("\n\n") + 1)
        return "ok", char_count(body), segments

    if "Show Notes AI 预览" in md or (
        "## 章节速览" in md and count_chapter_segments(md) > 0
    ):
        return "preview", char_count_preview(md), count_chapter_segments(md)

    return "unavailable", 0, 0


def fetch_transcript_md(track: dict) -> tuple[str, str, str, int, int]:
    """
    Always returns markdown text.
    Returns: md, status, error_note, charCount, segments
    """
    track_id = int(track["trackId"])
    notes_error = ""
    ai_intro: str | None = None
    chapters: list[tuple[str, str]] = []
    payload: dict | None = None

    # 1) Mobile「原文文稿」— requires XIMALAYA_COOKIE (login session)
    if get_cookie():
        try:
            asr_body = fetch_aidoc_text(track_id)
            if asr_body and not any(m in asr_body for m in PLACEHOLDER_MARKERS):
                try:
                    payload = fetch_shownotes(track_id)
                    ai_intro, chapters = parse_shownotes_payload(payload)
                except (urllib.error.URLError, ValueError, json.JSONDecodeError, OSError, PermissionError):
                    pass
                md = build_markdown_with_asr(track, ai_intro, chapters, asr_body)
                cc = char_count(asr_body)
                segs = max(1, asr_body.count("\n\n") + 1)
                return md, "ok", "", cc, segs
        except PermissionError as e:
            notes_error = str(e)
        except (urllib.error.URLError, json.JSONDecodeError, OSError, ValueError) as e:
            notes_error = f"aiDoc: {e}"

    # 2) Show Notes (+ optional aiDocUrl in same payload)
    try:
        payload = fetch_shownotes(track_id)
    except (urllib.error.URLError, ValueError, json.JSONDecodeError, OSError) as e:
        md = build_empty_markdown(track)
        err = notes_error or str(e)
        return md, "unavailable", err, 0, 0

    data = payload.get("data") or {}
    ai_doc_url = data.get("aiDocUrl")

    try:
        ai_intro, chapters = parse_shownotes_payload(payload)
    except ValueError as e:
        notes_error = notes_error or str(e)

    if ai_doc_url:
        try:
            asr_body = fetch_ai_document(str(ai_doc_url))
            if asr_body and not any(m in asr_body for m in PLACEHOLDER_MARKERS):
                md = build_markdown_with_asr(track, ai_intro, chapters, asr_body)
                cc = char_count(asr_body)
                segs = max(1, asr_body.count("\n\n") + 1)
                return md, "ok", "", cc, segs
        except (urllib.error.URLError, json.JSONDecodeError, OSError, ValueError) as e:
            notes_error = notes_error or f"aiDocUrl: {e}"

    if ai_intro or chapters:
        md = build_markdown(track, ai_intro, chapters)
        cc = char_count_preview(md)
        segs = count_chapter_segments(md)
        err = notes_error if notes_error else ""
        return md, "preview", err, cc, segs

    md = build_empty_markdown(track)
    err = notes_error or "no shownotes or aiIntro"
    if not get_cookie():
        err = f"{err}; set XIMALAYA_COOKIE for aiDoc/原文文稿"
    return md, "unavailable", err, 0, 0


def needs_refetch(md_path: Path) -> bool:
    if not md_path.is_file():
        return True
    status, _, _ = analyze_md(md_path.read_text(encoding="utf-8"))
    return status != "ok"


def index_row_for_track(
    track: dict,
    *,
    override: dict | None = None,
) -> dict[str, str]:
    md_path = transcript_path(track)
    rel = f"transcripts/{md_path.name}"
    status = "unavailable"
    cc = 0
    segs = 0
    error = ""

    if override:
        status = override.get("status", status)
        cc = int(override.get("charCount") or 0)
        segs = int(override.get("segments") or 0)
        error = override.get("error") or ""
    elif md_path.is_file():
        status, cc, segs = analyze_md(md_path.read_text(encoding="utf-8"))

    return {
        "index": str(track["index"]),
        "trackId": str(track["trackId"]),
        "title": track.get("title") or "",
        "duration": str(int(track.get("duration") or 0)),
        "status": status,
        "charCount": str(cc),
        "segments": str(segs),
        "transcriptFile": rel,
        "error": error,
        "publishedAt": track.get("publishedAt") or "",
        "playCount": str(int(track.get("playCount") or 0)),
    }


def write_index_csv(tracks: list[dict], overrides: dict[int, dict] | None = None) -> None:
    overrides = overrides or {}
    rows = [
        index_row_for_track(t, override=overrides.get(int(t["trackId"])))
        for t in sorted(tracks, key=lambda x: int(x["index"]))
    ]
    with INDEX_PATH.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=INDEX_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def save_tracks_json(tracks: list[dict]) -> None:
    TRACKS_PATH.write_text(
        json.dumps(tracks, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Sync album tracks from Ximalaya API and fetch new transcripts."
    )
    ap.add_argument("--album-id", type=int, default=DEFAULT_ALBUM_ID)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "--fetch-transcripts",
        action="store_true",
        help="Generate markdown for tracks missing transcript files",
    )
    ap.add_argument("--delay", type=float, default=2.0, help="Delay between transcript API calls")
    ap.add_argument("--timeout", type=float, default=60.0, help="HTTP timeout seconds for album API")
    ap.add_argument(
        "--skip-tracks-json",
        action="store_true",
        help="Only fetch transcripts; do not refresh tracks.json / index.csv",
    )
    ap.add_argument(
        "--reindex-from-api",
        action="store_true",
        help="Use API orderNo as index (may break article links)",
    )
    ap.add_argument(
        "--refetch-incomplete",
        action="store_true",
        help="Re-fetch transcripts that are not status=ok (needs XIMALAYA_COOKIE for 原文文稿)",
    )
    ap.add_argument("--from-index", type=int, default=0, help="Only refetch tracks with index >= N")
    ap.add_argument("--to-index", type=int, default=0, help="Only refetch tracks with index <= N")
    args = ap.parse_args()

    local = load_local_tracks()
    print(f"Local tracks: {len(local)}")

    if not args.skip_tracks_json:
        print(f"Fetching album {args.album_id} …")
        try:
            api_items = fetch_all_api_tracks(args.album_id, timeout=args.timeout)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as e:
            print(f"Album API failed: {e}")
            print("Tip: retry later or check network/VPN; shownotes fetch uses a separate API.")
            raise SystemExit(1) from e
        print(f"API tracks: {len(api_items)}")
        merged, new_ids, updated_ids = merge_tracks(
            local,
            api_items,
            reindex_from_api=args.reindex_from_api,
        )
        print(f"Merged: {len(merged)} (+{len(new_ids)} new, ~{len(updated_ids)} metadata updates)")
        if new_ids:
            for tid in new_ids:
                t = next(x for x in merged if int(x["trackId"]) == tid)
                print(f"  NEW index={t['index']} trackId={tid} title={t.get('title', '')[:40]}")
        if args.dry_run:
            print("dry-run: not writing tracks.json / index.csv")
        else:
            save_tracks_json(merged)
            write_index_csv(merged)
            print(f"Saved {TRACKS_PATH} and {INDEX_PATH}")
        tracks = merged
    else:
        tracks = local
        new_ids = []

    if not args.fetch_transcripts and not args.refetch_incomplete:
        print("Done (use --fetch-transcripts to generate new markdown files)")
        return

    if args.refetch_incomplete and not args.fetch_transcripts:
        args.fetch_transcripts = True

    missing = [t for t in tracks if not transcript_path(t).is_file()]
    if args.refetch_incomplete:
        for t in tracks:
            idx = int(t["index"])
            if args.from_index and idx < args.from_index:
                continue
            if args.to_index and idx > args.to_index:
                continue
            if needs_refetch(transcript_path(t)) and t not in missing:
                missing.append(t)
    if not missing:
        print("No missing or incomplete transcript files.")
        return

    print(f"Fetching {len(missing)} transcript(s) …")
    overrides: dict[int, dict] = {}
    for i, track in enumerate(missing):
        tid = int(track["trackId"])
        out = transcript_path(track)
        md, status, err, cc, segs = fetch_transcript_md(track)
        tag = {"ok": "full", "preview": "preview", "unavailable": "stub"}[status]
        if args.dry_run:
            print(f"[DRY {tag}] {tid} -> {out.name} status={status} err={err[:60] if err else '-'}")
        else:
            out.write_text(md, encoding="utf-8", newline="\n")
            overrides[tid] = {
                "status": status,
                "charCount": cc,
                "segments": segs,
                "error": err,
            }
            print(f"[OK {tag}] {tid} -> {out.name} status={status}")

        if args.delay and i < len(missing) - 1:
            time.sleep(args.delay)

    if not args.dry_run and not args.skip_tracks_json:
        write_index_csv(tracks, overrides=overrides)
        print(f"Updated {INDEX_PATH} for {len(overrides)} new transcript(s)")

    print("Done.")


if __name__ == "__main__":
    main()

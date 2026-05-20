#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sync publish time (from Show Notes API) and play count (from tracks.json) across the repo."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

from data_bundle import load_data, save_data  # noqa: E402
CONTENT = REPO / "content"
TRACKS_PATH = CONTENT / "tracks.json"
INDEX_PATH = CONTENT / "index.csv"
TRANSCRIPTS_DIR = CONTENT / "transcripts"

META_PUBLISHED = re.compile(r"^- 发布时间：.*$", re.M)
META_PLAY = re.compile(r"^- 播放量：.*$", re.M)
META_LINK = re.compile(r"^- 原链接：.*$", re.M)

sys.path.insert(0, str(REPO / "scripts" / "transcripts"))
from fetch_shownotes_fallback import fetch_shownotes  # noqa: E402


def format_published_at(ms: int) -> str:
    return datetime.fromtimestamp(int(ms) / 1000).strftime("%Y-%m-%d %H:%M:%S")


def fetch_published_at(track_id: int) -> str | None:
    try:
        payload = fetch_shownotes(track_id)
    except Exception:
        return None
    data = payload.get("data") or {}
    ms = data.get("trackCreateTime")
    if ms is None:
        return None
    return format_published_at(int(ms))


def parse_md_meta(text: str) -> tuple[str | None, int | None]:
    published_at: str | None = None
    play_count: int | None = None
    for line in text.splitlines():
        stripped = line.strip()
        m = re.match(r"^- 发布时间：(.+)$", stripped)
        if m:
            published_at = m.group(1).strip()
        m = re.match(r"^- 播放量：(\d+)$", stripped)
        if m:
            play_count = int(m.group(1))
    return published_at, play_count


def patch_markdown(text: str, published_at: str | None, play_count: int | None) -> str:
    lines = text.splitlines()
    out: list[str] = []
    has_pub = bool(META_PUBLISHED.search(text))
    has_play = bool(META_PLAY.search(text))
    inserted = False

    for line in lines:
        if line.startswith("- 发布时间："):
            if published_at:
                out.append(f"- 发布时间：{published_at}")
            continue
        if line.startswith("- 播放量："):
            if play_count is not None:
                out.append(f"- 播放量：{play_count}")
            continue
        out.append(line)
        if not inserted and META_LINK.match(line):
            if published_at and not has_pub:
                out.append(f"- 发布时间：{published_at}")
            if play_count is not None and not has_play:
                out.append(f"- 播放量：{play_count}")
            inserted = True

    if not inserted and (published_at or play_count is not None):
        rebuilt: list[str] = []
        for i, line in enumerate(out):
            rebuilt.append(line)
            if line.startswith("- 原链接：") and i + 1 < len(out) and out[i + 1] == "":
                if published_at and not has_pub:
                    rebuilt.append(f"- 发布时间：{published_at}")
                if play_count is not None and not has_play:
                    rebuilt.append(f"- 播放量：{play_count}")
        out = rebuilt

    return "\n".join(out) + ("\n" if text.endswith("\n") else "")


def load_tracks() -> list[dict]:
    return json.loads(TRACKS_PATH.read_text(encoding="utf-8"))


def save_tracks(tracks: list[dict]) -> None:
    TRACKS_PATH.write_text(
        json.dumps(tracks, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def build_by_id(all_tracks: list[dict]) -> dict[int, dict]:
    by_id: dict[int, dict] = {}
    for track in all_tracks:
        tid = int(track["trackId"])
        by_id[tid] = {
            "publishedAt": track.get("publishedAt"),
            "playCount": track.get("playCount"),
        }
    return by_id


def apply_meta_to_data(data: dict, by_id: dict[int, dict]) -> None:
    for t in data.get("tracks", []):
        tid = int(t["trackId"])
        meta = by_id.get(tid)
        if not meta:
            continue
        if meta.get("publishedAt"):
            t["publishedAt"] = meta["publishedAt"]
        elif "publishedAt" in t:
            del t["publishedAt"]
        if meta.get("playCount") is not None:
            t["playCount"] = int(meta["playCount"])
        elif "playCount" in t:
            del t["playCount"]


def update_index_csv(by_id: dict[int, dict]) -> None:
    rows: list[dict[str, str]] = []
    with INDEX_PATH.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        for col in ("publishedAt", "playCount"):
            if col not in fieldnames:
                fieldnames.append(col)
        for row in reader:
            tid = int(row["trackId"])
            meta = by_id.get(tid)
            if meta:
                if meta.get("publishedAt"):
                    row["publishedAt"] = meta["publishedAt"]
                if meta.get("playCount") is not None:
                    row["playCount"] = str(meta["playCount"])
            rows.append(row)
    with INDEX_PATH.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def patch_all_markdown(all_tracks: list[dict], by_id: dict[int, dict]) -> int:
    md_updated = 0
    for track in all_tracks:
        tid = int(track["trackId"])
        meta = by_id.get(tid)
        if not meta:
            continue
        md_path = TRANSCRIPTS_DIR / f"{int(track['index']):03d}_{tid}.md"
        if not md_path.is_file():
            continue
        text = md_path.read_text(encoding="utf-8")
        new_text = patch_markdown(
            text,
            meta.get("publishedAt"),
            meta.get("playCount"),
        )
        if new_text != text:
            md_path.write_text(new_text, encoding="utf-8", newline="\n")
            md_updated += 1
    return md_updated


def main() -> None:
    ap = argparse.ArgumentParser(description="Sync publishedAt and playCount to data.js, CSV, markdown.")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--delay", type=float, default=0.5, help="Delay between Show Notes API calls")
    ap.add_argument(
        "--skip-fetch",
        action="store_true",
        help="Do not call API; only merge tracks.json fields into data.js / CSV / markdown",
    )
    ap.add_argument("--resume", action="store_true", help="Skip tracks that already have publishedAt")
    ap.add_argument("--track-id", type=int, default=0, help="Single trackId to process")
    args = ap.parse_args()

    all_tracks = load_tracks()
    track_by_id = {int(t["trackId"]): t for t in all_tracks}
    data = load_data()
    data_by_id = {int(t["trackId"]): t for t in data.get("tracks", [])}

    if args.track_id:
        work = [t for t in all_tracks if int(t["trackId"]) == args.track_id]
    elif args.limit:
        work = all_tracks[: args.limit]
    else:
        work = all_tracks

    fetched = 0
    skipped = 0
    for i, track in enumerate(work):
        tid = int(track["trackId"])
        play_count = track.get("playCount")
        md_path = TRANSCRIPTS_DIR / f"{int(track['index']):03d}_{tid}.md"
        if md_path.is_file():
            md_pub, md_play = parse_md_meta(md_path.read_text(encoding="utf-8"))
            if md_pub:
                published_at = md_pub
                track["publishedAt"] = md_pub
            if md_play is not None:
                play_count = md_play
                track["playCount"] = md_play

        if args.skip_fetch:
            published_at = track.get("publishedAt")
        else:
            published_at = track.get("publishedAt")
            if args.resume and published_at:
                skipped += 1
            else:
                got = fetch_published_at(tid)
                if got:
                    published_at = got
                    track["publishedAt"] = got
                    fetched += 1
                if args.delay and i < len(work) - 1:
                    time.sleep(args.delay)

        if args.dry_run:
            continue

        dt = data_by_id.get(tid)
        if dt:
            if published_at:
                dt["publishedAt"] = published_at
            if play_count is not None:
                dt["playCount"] = int(play_count)

        if not args.skip_fetch and (i + 1) % 10 == 0:
            save_tracks(all_tracks)
            apply_meta_to_data(data, build_by_id(all_tracks))
            save_data(data)
            print(f"checkpoint {i + 1}/{len(work)} fetched={fetched} skipped={skipped}")

    if args.dry_run:
        print(f"dry-run: would process {len(work)} tracks")
        return

    save_tracks(all_tracks)
    by_id = build_by_id(all_tracks)
    apply_meta_to_data(data, by_id)
    save_data(data)
    update_index_csv(by_id)
    md_updated = patch_all_markdown(all_tracks, by_id)

    with_pub = sum(1 for t in all_tracks if t.get("publishedAt"))
    with_play = sum(1 for t in all_tracks if t.get("playCount") is not None)
    print(f"Saved {TRACKS_PATH}, data-index.js, {INDEX_PATH}")
    print(
        f"publishedAt: {with_pub}/{len(all_tracks)}, playCount: {with_play}/{len(all_tracks)}, "
        f"markdown patched: {md_updated}, fetched: {fetched}, skipped: {skipped}"
    )


if __name__ == "__main__":
    main()

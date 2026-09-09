#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
One-shot local sync for Windows background automation:

  1. Read XIMALAYA_COOKIE from Chrome/Edge (no manual copy)
  2. Sync album + fetch aiDoc transcripts (China network)
  3. Whisper fallback for tracks still without full text
  4. Rebuild site data + optional git commit/push

Usage:
  python scripts/transcripts/sync_local.py
  python scripts/transcripts/sync_local.py --no-push
  python scripts/transcripts/sync_local.py --whisper-only
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CONTENT = REPO / "content"
INDEX_PATH = CONTENT / "index.csv"
TRACKS_PATH = CONTENT / "tracks.json"
TRANSCRIPTS_DIR = CONTENT / "transcripts"
AUDIO_CACHE = REPO / "_agent" / "audio"
LOG_DIR = REPO / "_agent" / "logs"

sys.path.insert(0, str(Path(__file__).resolve().parent))

from browser_cookie import cookie_diagnostics, ensure_cookie_env  # noqa: E402
from fetch_aidoc import fetch_aidoc_payload  # noqa: E402
from sync_album_from_api import (  # noqa: E402
    analyze_md,
    build_markdown_with_asr,
    char_count,
    fetch_shownotes,
    load_local_tracks,
    parse_shownotes_payload,
    transcript_path,
    write_index_csv,
)
from transcribe_whisper import transcribe_file  # noqa: E402
from ximalaya_audio import download_track  # noqa: E402


PROBE_TRACK_ID = 980020064


class Logger:
    def __init__(self, log_path: Path | None) -> None:
        self._path = log_path
        if log_path:
            log_path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, msg: str) -> None:
        line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
        print(line, flush=True)
        if self._path:
            with self._path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")


def verify_cookie(cookie: str, log: Logger) -> bool:
    diag = cookie_diagnostics(cookie)
    log.log(f"cookie: length={diag.get('length')} login={diag.get('has_login_markers')}")
    if not diag.get("has_login_markers"):
        log.log("ERROR: browser cookie missing login markers — open www.ximalaya.com and log in")
        return False
    try:
        fetch_aidoc_payload(PROBE_TRACK_ID, cookie=cookie)
        log.log(f"aiDoc probe OK (track {PROBE_TRACK_ID})")
        return True
    except Exception as e:
        log.log(f"aiDoc probe FAILED: {e}")
        return False


def load_tracks_by_id() -> dict[int, dict]:
    data = json.loads(TRACKS_PATH.read_text(encoding="utf-8"))
    return {int(t["trackId"]): t for t in data}


def incomplete_tracks(from_index: int = 0) -> list[dict]:
    tracks = load_tracks_by_id()
    rows: list[dict] = []
    with INDEX_PATH.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            idx = int(row["index"])
            if from_index and idx < from_index:
                continue
            status = row.get("status") or ""
            if status == "ok":
                continue
            tid = int(row["trackId"])
            track = tracks.get(tid)
            if track:
                rows.append(track)
    return sorted(rows, key=lambda t: int(t["index"]))


def run_api_sync(args: argparse.Namespace, log: Logger) -> None:
    cmd = [
        sys.executable,
        str(REPO / "scripts/transcripts/sync_album_from_api.py"),
        "--fetch-transcripts",
        "--refetch-incomplete",
        "--delay",
        str(args.delay),
    ]
    if args.from_index:
        cmd.extend(["--from-index", str(args.from_index)])
    log.log("run: " + " ".join(cmd))
    subprocess.run(cmd, cwd=REPO, check=True)


def whisper_fallback(
    tracks: list[dict],
    cookie: str,
    log: Logger,
    *,
    model: str,
    device: str,
    compute_type: str,
    keep_audio: bool,
) -> dict[int, dict]:
    overrides: dict[int, dict] = {}
    for i, track in enumerate(tracks):
        tid = int(track["trackId"])
        out_md = transcript_path(track)
        if out_md.is_file():
            status, _, _ = analyze_md(out_md.read_text(encoding="utf-8"))
            if status == "ok":
                continue

        audio_path = AUDIO_CACHE / f"{tid}.m4a"
        log.log(f"whisper [{i+1}/{len(tracks)}] trackId={tid} index={track['index']}")

        try:
            download_track(tid, audio_path, cookie)
        except Exception as e:
            log.log(f"  download failed: {e}")
            overrides[tid] = {
                "status": "unavailable",
                "charCount": 0,
                "segments": 0,
                "error": f"audio download: {e}",
            }
            continue

        try:
            asr_body = transcribe_file(
                audio_path,
                model_size=model,
                device=device,
                compute_type=compute_type,
            )
        except Exception as e:
            log.log(f"  whisper failed: {e}")
            overrides[tid] = {
                "status": "unavailable",
                "charCount": 0,
                "segments": 0,
                "error": f"whisper: {e}",
            }
            continue

        if not asr_body or char_count(asr_body) < 80:
            log.log("  whisper output too short")
            overrides[tid] = {
                "status": "unavailable",
                "charCount": 0,
                "segments": 0,
                "error": "whisper output too short",
            }
            continue

        ai_intro = None
        chapters: list[tuple[str, str]] = []
        try:
            payload = fetch_shownotes(tid, cookie=cookie)
            ai_intro, chapters = parse_shownotes_payload(payload)
        except Exception:
            pass

        md = build_markdown_with_asr(track, ai_intro, chapters, asr_body)
        out_md.write_text(md, encoding="utf-8", newline="\n")
        cc = char_count(asr_body)
        segs = max(1, asr_body.count("\n\n") + 1)
        overrides[tid] = {"status": "ok", "charCount": cc, "segments": segs, "error": "whisper-local"}
        log.log(f"  OK chars={cc}")

        if not keep_audio:
            try:
                audio_path.unlink(missing_ok=True)
            except OSError:
                pass

    return overrides


def rebuild_site(log: Logger) -> None:
    for script in (
        "scripts/transcripts/normalize_transcripts.py",
        "scripts/site/rebuild_data_js.py",
        "scripts/site/update_library_date.py",
    ):
        cmd = [sys.executable, str(REPO / script)]
        log.log("run: " + " ".join(cmd))
        subprocess.run(cmd, cwd=REPO, check=True)


def git_push(log: Logger, message: str) -> None:
    subprocess.run(["git", "add", "content", "data-index.js", "content/articles", "index.html"], cwd=REPO)
    st = subprocess.run(["git", "diff", "--staged", "--quiet"], cwd=REPO)
    if st.returncode == 0:
        log.log("git: no changes to commit")
        return
    subprocess.run(["git", "commit", "-m", message], cwd=REPO, check=True)
    subprocess.run(["git", "push"], cwd=REPO, check=True)
    log.log("git: pushed")


def main() -> None:
    ap = argparse.ArgumentParser(description="Local full sync (cookie + api + whisper)")
    ap.add_argument("--no-push", action="store_true", help="Skip git commit/push")
    ap.add_argument("--no-whisper", action="store_true", help="Skip whisper fallback")
    ap.add_argument("--whisper-only", action="store_true", help="Only run whisper on incomplete tracks")
    ap.add_argument("--from-index", type=int, default=0)
    ap.add_argument("--delay", type=float, default=1.5)
    ap.add_argument("--whisper-model", default=os.environ.get("WHISPER_MODEL", "small"))
    ap.add_argument("--whisper-device", default=os.environ.get("WHISPER_DEVICE", "auto"))
    ap.add_argument("--whisper-compute", default=os.environ.get("WHISPER_COMPUTE", "int8"))
    ap.add_argument("--keep-audio", action="store_true", help="Keep downloaded audio in _agent/audio")
    ap.add_argument("--log-file", type=Path, default=None)
    args = ap.parse_args()

    log_path = args.log_file or (LOG_DIR / f"sync-{datetime.now().strftime('%Y%m%d-%H%M%S')}.log")
    log = Logger(log_path)
    log.log("=== sync_local start ===")

    try:
        cookie = ensure_cookie_env()
    except RuntimeError as e:
        log.log(f"ERROR: {e}")
        raise SystemExit(1) from e

    if not verify_cookie(cookie, log):
        log.log("Aborting: fix browser login first")
        raise SystemExit(2)

    if not args.whisper_only:
        run_api_sync(args, log)

    if not args.no_whisper:
        pending = incomplete_tracks(from_index=args.from_index)
        if pending:
            log.log(f"whisper queue: {len(pending)} track(s)")
            tracks_all = load_local_tracks()
            overrides = whisper_fallback(
                pending,
                cookie,
                log,
                model=args.whisper_model,
                device=args.whisper_device,
                compute_type=args.whisper_compute,
                keep_audio=args.keep_audio,
            )
            if overrides:
                write_index_csv(tracks_all, overrides=overrides)
                log.log(f"index.csv updated for {len(overrides)} whisper track(s)")
        else:
            log.log("whisper queue empty")

    rebuild_site(log)

    if not args.no_push:
        try:
            git_push(log, "chore: local sync Ximalaya transcripts")
        except subprocess.CalledProcessError as e:
            log.log(f"git push skipped/failed: {e}")

    log.log("=== sync_local done ===")


if __name__ == "__main__":
    main()

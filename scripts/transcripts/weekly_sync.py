#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Weekly sync orchestrator:
1) Refresh album list / fetch aiDoc or shownotes transcripts
2) For incomplete tracks: download audio in .venv and run local ASR
3) Polish text + generate chapter TOC + SmartArt diagrams
4) Rebuild site data
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PY = REPO / ".venv" / "bin" / "python"
if not PY.is_file():
    PY = Path(sys.executable)

SCRIPTS = REPO / "scripts" / "transcripts"
SITE = REPO / "scripts" / "site"
CONTENT = REPO / "content"
AUDIO_DIR = CONTENT / "audio"
ASR_DIR = CONTENT / "asr_raw"
POLISHED_DIR = CONTENT / "polished"


def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    print("+", " ".join(cmd), flush=True)
    return subprocess.run(cmd, cwd=str(REPO), check=check)


def load_index_incomplete(from_index: int = 0, limit: int = 0) -> list[dict]:
    import csv

    rows = []
    with (CONTENT / "index.csv").open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            idx = int(row["index"])
            if from_index and idx < from_index:
                continue
            if limit and len(rows) >= limit:
                break
            if row.get("status") != "ok":
                rows.append(row)
    return rows


def local_asr_for_row(row: dict, *, model: str = "tiny") -> Path | None:
    sys.path.insert(0, str(SCRIPTS))
    from download_audio import download_track_audio  # noqa: WPS433
    from asr_local import transcribe_audio  # noqa: WPS433
    from sync_album_from_api import (  # noqa: WPS433
        build_markdown_with_asr,
        load_local_tracks,
        transcript_path,
        write_index_csv,
    )
    from fetch_shownotes_fallback import fetch_shownotes, parse_shownotes_payload

    track_id = int(row["trackId"])
    index = int(row["index"])
    tracks = {int(t["trackId"]): t for t in load_local_tracks()}
    track = tracks.get(track_id)
    if not track:
        track = {
            "index": index,
            "trackId": track_id,
            "title": row.get("title") or f"track {track_id}",
            "duration": int(row.get("duration") or 0),
            "url": f"/sound/{track_id}",
            "albumTitle": "盛世裕丰",
            "anchorName": "盛世裕丰财富之道",
            "publishedAt": row.get("publishedAt") or "",
            "playCount": int(row.get("playCount") or 0),
        }

    print(f"[ASR] download track {track_id} …", flush=True)
    try:
        audio = download_track_audio(track_id, index=index, prefer="ytdlp")
    except Exception as e:
        print(f"[ASR] download failed: {e}", flush=True)
        return None

    print(f"[ASR] transcribe {audio.name} with model={model} …", flush=True)
    ASR_DIR.mkdir(parents=True, exist_ok=True)
    result = transcribe_audio(audio, model_size=model)
    raw_json = ASR_DIR / f"{index:03d}_{track_id}.json"
    raw_json.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    ai_intro = None
    chapters: list[tuple[str, str]] = []
    try:
        payload = fetch_shownotes(track_id)
        ai_intro, chapters = parse_shownotes_payload(payload)
    except Exception:
        pass

    # If shownotes chapters missing, synthesize from ASR segment timestamps
    if not chapters and result.get("segments"):
        segs = result["segments"]
        step = max(1, len(segs) // 10)
        for i in range(0, len(segs), step):
            s = segs[i]
            ts = int(s["start"])
            mm, ss = divmod(ts, 60)
            title = (s["text"] or "")[:24] or f"段落 {i // step + 1}"
            chapters.append((f"{mm:02d}:{ss:02d}", title))

    body = result.get("text") or ""
    if not body.strip():
        print("[ASR] empty transcription", flush=True)
        return None

    md = build_markdown_with_asr(track, ai_intro, chapters, body)
    out = transcript_path(track)
    out.write_text(md, encoding="utf-8", newline="\n")
    # refresh index row status
    all_tracks = load_local_tracks()
    write_index_csv(
        all_tracks,
        overrides={
            track_id: {
                "status": "ok",
                "charCount": result.get("charCount") or len(body),
                "segments": max(1, body.count("\n\n") + 1),
                "error": "",
            }
        },
    )
    print(f"[ASR] wrote {out} chars={result.get('charCount')}", flush=True)
    return out


def polish_path(md_path: Path) -> None:
    run([str(PY), str(SCRIPTS / "polish_transcript.py"), "--file", str(md_path)])


def main() -> None:
    ap = argparse.ArgumentParser(description="Weekly Ximalaya sync + local ASR + polish")
    ap.add_argument("--skip-album-sync", action="store_true")
    ap.add_argument("--skip-local-asr", action="store_true")
    ap.add_argument("--skip-polish", action="store_true")
    ap.add_argument("--skip-rebuild", action="store_true")
    ap.add_argument("--asr-limit", type=int, default=1, help="Max incomplete tracks for local ASR")
    ap.add_argument("--asr-from-index", type=int, default=0)
    ap.add_argument("--asr-model", default="tiny")
    ap.add_argument("--track-id", type=int, default=0, help="Force local ASR for one trackId")
    args = ap.parse_args()

    if not args.skip_album_sync:
        run(
            [
                str(PY),
                str(SCRIPTS / "sync_album_from_api.py"),
                "--fetch-transcripts",
                "--refetch-incomplete",
                "--delay",
                "1.2",
                "--timeout",
                "90",
            ]
        )

    targets: list[Path] = []
    if not args.skip_local_asr:
        if args.track_id:
            import csv

            row = None
            with (CONTENT / "index.csv").open(encoding="utf-8", newline="") as f:
                for r in csv.DictReader(f):
                    if int(r["trackId"]) == args.track_id:
                        row = r
                        break
            if not row:
                # fabricate from tracks.json
                tracks = json.loads((CONTENT / "tracks.json").read_text(encoding="utf-8"))
                t = next(x for x in tracks if int(x["trackId"]) == args.track_id)
                row = {
                    "index": str(t["index"]),
                    "trackId": str(t["trackId"]),
                    "title": t.get("title") or "",
                    "duration": str(t.get("duration") or 0),
                    "status": "preview",
                    "publishedAt": t.get("publishedAt") or "",
                    "playCount": str(t.get("playCount") or 0),
                }
            md = local_asr_for_row(row, model=args.asr_model)
            if md:
                targets.append(md)
        else:
            rows = load_index_incomplete(from_index=args.asr_from_index, limit=args.asr_limit)
            print(f"Incomplete candidates for local ASR: {len(rows)}", flush=True)
            for row in rows:
                md = local_asr_for_row(row, model=args.asr_model)
                if md:
                    targets.append(md)
                time.sleep(0.5)

    if not args.skip_polish:
        if not targets:
            # polish newest transcript if present
            newest = sorted((CONTENT / "transcripts").glob("*.md"))
            if newest:
                targets = [newest[-1]]
        for md in targets:
            try:
                polish_path(md)
            except Exception as e:
                print(f"[polish] failed for {md}: {e}", flush=True)

    if not args.skip_rebuild:
        run([str(PY), str(SITE / "rebuild_data_js.py")])
        run([str(PY), str(SITE / "update_library_date.py")])

    print("Weekly sync done.")
    if POLISHED_DIR.is_dir():
        latest = sorted(POLISHED_DIR.glob("*.md"))
        if latest:
            print(f"Latest polished: {latest[-1]}")


if __name__ == "__main__":
    main()

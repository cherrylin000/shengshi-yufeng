#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Download Ximalaya track audio into content/audio/ (yt-dlp + shownotes URL fallback)."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
AUDIO_DIR = REPO / "content" / "audio"
MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_shownotes_fallback import fetch_shownotes  # noqa: E402


def find_yt_dlp() -> str | None:
    for cand in (
        REPO / ".venv" / "bin" / "yt-dlp",
        shutil.which("yt-dlp"),
    ):
        if not cand:
            continue
        p = Path(cand) if not isinstance(cand, Path) else cand
        if p.is_file() or shutil.which(str(cand)):
            return str(cand)
    return None


def shownotes_play_url(track_id: int) -> str | None:
    try:
        payload = fetch_shownotes(track_id)
    except Exception:
        return None
    data = payload.get("data") or {}
    url = data.get("url")
    if isinstance(url, str) and url.startswith("http"):
        return url
    return None


def download_via_url(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(
        url,
        headers={"User-Agent": MOBILE_UA, "Referer": "https://www.ximalaya.com/"},
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        dest.write_bytes(resp.read())
    return dest


def download_via_ytdlp(track_id: int, dest_stem: Path, *, format_id: str = "24k") -> Path:
    yt = find_yt_dlp()
    if not yt:
        raise RuntimeError("yt-dlp not found; install into .venv or PATH")
    dest_stem.parent.mkdir(parents=True, exist_ok=True)
    outtmpl = str(dest_stem) + ".%(ext)s"
    cmd = [
        yt,
        "-f",
        format_id,
        "-o",
        outtmpl,
        f"https://www.ximalaya.com/sound/{track_id}",
    ]
    subprocess.run(cmd, check=True)
    matches = sorted(dest_stem.parent.glob(dest_stem.name + ".*"))
    matches = [p for p in matches if p.suffix.lower() in {".m4a", ".mp3", ".aac", ".wav", ".ogg"}]
    if not matches:
        raise FileNotFoundError(f"yt-dlp finished but no audio under {dest_stem}.*")
    return matches[0]


def download_track_audio(
    track_id: int,
    *,
    index: int | None = None,
    prefer: str = "shownotes",
    format_id: str = "24k",
) -> Path:
    """
    Download audio for track_id.
    prefer: shownotes | ytdlp
    """
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    prefix = f"{int(index):03d}_" if index is not None else ""
    stem = AUDIO_DIR / f"{prefix}{track_id}"

    existing = list(AUDIO_DIR.glob(f"{prefix}{track_id}.*"))
    existing = [p for p in existing if p.suffix.lower() in {".m4a", ".mp3", ".aac", ".wav", ".ogg"}]
    if existing:
        return existing[0]

    errors: list[str] = []
    order = ["shownotes", "ytdlp"] if prefer == "shownotes" else ["ytdlp", "shownotes"]
    for method in order:
        try:
            if method == "shownotes":
                url = shownotes_play_url(track_id)
                if not url:
                    raise RuntimeError("shownotes has no play url")
                ext = ".m4a" if ".m4a" in url else ".mp3"
                return download_via_url(url, stem.with_suffix(ext))
            return download_via_ytdlp(track_id, stem, format_id=format_id)
        except Exception as e:
            errors.append(f"{method}: {e}")
    raise RuntimeError("; ".join(errors))


def main() -> None:
    ap = argparse.ArgumentParser(description="Download Ximalaya track audio")
    ap.add_argument("track_id", type=int)
    ap.add_argument("--index", type=int, default=None)
    ap.add_argument("--prefer", choices=("shownotes", "ytdlp"), default="shownotes")
    ap.add_argument("--format", dest="format_id", default="24k")
    args = ap.parse_args()
    path = download_track_audio(
        args.track_id, index=args.index, prefer=args.prefer, format_id=args.format_id
    )
    print(json.dumps({"trackId": args.track_id, "path": str(path), "bytes": path.stat().st_size}, ensure_ascii=False))


if __name__ == "__main__":
    main()

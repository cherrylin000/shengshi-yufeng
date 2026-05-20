#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Split site data: data-index.js (no transcripts) + content/articles/{index}.json."""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
INDEX_JS = REPO / "data-index.js"
LEGACY_JS = REPO / "data.js"
ARTICLES_DIR = REPO / "content" / "articles"

# 仅全文进单篇 JSON；简介与章节速览留在索引供列表筛选与预览
ARTICLE_KEYS = frozenset({"content"})


def _read_js_payload(path: Path, global_name: str) -> dict:
    raw = path.read_text(encoding="utf-8")
    prefix = f"window.{global_name} = "
    if not raw.startswith(prefix):
        raise ValueError(f"{path}: expected {prefix!r} prefix")
    return json.loads(raw[len(prefix) :].strip().rstrip(";"))


def _write_js(path: Path, global_name: str, data: dict) -> None:
    body = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    path.write_text(f"window.{global_name} = {body};\n", encoding="utf-8")


def article_path(index: int) -> Path:
    return ARTICLES_DIR / f"{int(index):03d}.json"


def build_search_text(track: dict) -> str:
    parts = [track.get("title") or ""]
    intro = track.get("intro")
    if intro:
        parts.append(intro)
    for item in track.get("outline") or []:
        parts.append(f"{item.get('time', '')}{item.get('title', '')}")
    return re.sub(r"\s+", "", "".join(parts)).lower()


def slim_track(track: dict) -> dict:
    slim = {k: v for k, v in track.items() if k not in ARTICLE_KEYS}
    slim["searchText"] = build_search_text(track)
    if track.get("content") or track.get("status") == "ok":
        slim["hasArticle"] = True
    return slim


def article_payload(track: dict) -> dict | None:
    payload = {k: track[k] for k in ARTICLE_KEYS if k in track and track[k]}
    if not payload:
        return None
    payload["index"] = int(track["index"])
    payload["trackId"] = track["trackId"]
    return payload


def load_index() -> dict:
    if INDEX_JS.is_file():
        return _read_js_payload(INDEX_JS, "SHENGSHI_INDEX")
    if LEGACY_JS.is_file():
        data = _read_js_payload(LEGACY_JS, "SHENGSHI_DATA")
        return {**data, "tracks": [slim_track(t) for t in data.get("tracks", [])]}
    raise FileNotFoundError("data-index.js / data.js not found")


def load_article(index: int) -> dict | None:
    path = article_path(index)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def load_data() -> dict:
    """Full in-memory dataset for build scripts (index + article bodies)."""
    if LEGACY_JS.is_file() and not INDEX_JS.is_file():
        return _read_js_payload(LEGACY_JS, "SHENGSHI_DATA")
    data = load_index()
    tracks = []
    for t in data.get("tracks", []):
        merged = dict(t)
        art = load_article(int(t["index"]))
        if art:
            merged.update({k: v for k, v in art.items() if k not in ("index", "trackId")})
        tracks.append(merged)
    return {**data, "tracks": tracks}


def save_bundle(data: dict) -> None:
    ARTICLES_DIR.mkdir(parents=True, exist_ok=True)
    seen: set[int] = set()
    index_tracks = []
    for track in data.get("tracks", []):
        idx = int(track["index"])
        seen.add(idx)
        art = article_payload(track)
        if art:
            article_path(idx).write_text(
                json.dumps(art, ensure_ascii=False, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
        else:
            p = article_path(idx)
            if p.is_file():
                p.unlink()
        index_tracks.append(slim_track(track))

    for path in ARTICLES_DIR.glob("*.json"):
        try:
            n = int(path.stem)
        except ValueError:
            continue
        if n not in seen:
            path.unlink()

    index_data = {k: v for k, v in data.items() if k != "tracks"}
    index_data["tracks"] = index_tracks
    _write_js(INDEX_JS, "SHENGSHI_INDEX", index_data)


def save_data(data: dict) -> None:
    save_bundle(data)


def migrate_legacy() -> None:
    if not LEGACY_JS.is_file():
        raise SystemExit(f"Missing {LEGACY_JS}")
    data = _read_js_payload(LEGACY_JS, "SHENGSHI_DATA")
    save_bundle(data)
    print(f"Wrote {INDEX_JS.name} + {ARTICLES_DIR.relative_to(REPO)}/")


if __name__ == "__main__":
    migrate_legacy()

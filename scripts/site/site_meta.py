#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Recompute site-wide counts from tracks and patch corpus-size copy."""

from __future__ import annotations

import re
from typing import Any

CORPUS_COUNT_RE = re.compile(r"本目录下 \d+ 份可用音频")


def recompute_meta(data: dict) -> dict[str, int]:
    tracks = data.get("tracks") or []
    ok = sum(1 for t in tracks if t.get("status") == "ok")
    char_total = sum(int(t.get("charCount") or 0) for t in tracks if t.get("status") == "ok")
    stats = {
        "trackCount": len(tracks),
        "okCount": ok,
        "missingCount": len(tracks) - ok,
        "charTotal": char_total,
    }
    meta = data.setdefault("meta", {})
    meta.update(stats)
    patch_corpus_counts(data, ok)
    return stats


def patch_corpus_counts(data: dict, ok_count: int | None = None) -> None:
    ok_count = ok_count if ok_count is not None else int(data.get("meta", {}).get("okCount") or 0)
    replacement = f"本目录下 {ok_count} 份可用音频"

    for key in ("systemHtml",):
        val = data.get(key)
        if isinstance(val, str):
            data[key] = CORPUS_COUNT_RE.sub(replacement, val)

    sections = data.get("systemSections")
    if isinstance(sections, dict):
        data["systemSections"] = {
            k: _patch_corpus_in_node(v, replacement) for k, v in sections.items()
        }


def _patch_corpus_in_node(node: Any, replacement: str) -> Any:
    if isinstance(node, str):
        return CORPUS_COUNT_RE.sub(replacement, node)
    if isinstance(node, dict):
        return {k: _patch_corpus_in_node(v, replacement) for k, v in node.items()}
    if isinstance(node, list):
        return [_patch_corpus_in_node(item, replacement) for item in node]
    return node

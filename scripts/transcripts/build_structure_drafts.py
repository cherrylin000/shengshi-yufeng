#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build 结构稿 markdown for every track. Does not overwrite polished transcripts."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CONTENT = REPO / "content"
TRANSCRIPTS = CONTENT / "transcripts"
POLISHED = CONTENT / "polished"
OUT_DIR = CONTENT / "structured"

SKIP_HANDCRAFTED = {392}

CHAPTER_LINE = re.compile(r"^- (\d{1,2}:\d{2}(?::\d{2})?)\s+(.+?)\s*$")
CHAPTER_NUM = re.compile(
    r"^\d+\.\s+\*\*(\d{1,2}:\d{2}(?::\d{2})?)\*\*\s+(.+?)\s*$"
)
LEAD = re.compile(
    r"^(所以呢?|其实呢?|那么呢?|就是说?|这个|那个|然后呢?|我觉得|我看|大家|咱们)+"
)


def split_sections(md: str) -> dict[str, str]:
    parts: dict[str, list[str]] = {"_preamble": []}
    current = "_preamble"
    for line in md.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            parts.setdefault(current, [])
            continue
        parts.setdefault(current, []).append(line)
    return {k: "\n".join(v).strip() for k, v in parts.items()}


def parse_meta(preamble: str) -> dict[str, str]:
    meta = {}
    for line in preamble.splitlines():
        m = re.match(r"^#\s+(.+)$", line.strip())
        if m:
            meta["title"] = m.group(1).strip()
            continue
        m = re.match(r"^- (.+?)：(.+)$", line.strip())
        if m:
            meta[m.group(1)] = m.group(2).strip()
    return meta


def parse_chapters(md: str) -> list[tuple[str, str]]:
    secs = split_sections(md)
    block = secs.get("章节目录") or secs.get("章节速览") or ""
    out: list[tuple[str, str]] = []
    for line in block.splitlines():
        m = CHAPTER_NUM.match(line.strip()) or CHAPTER_LINE.match(line.strip())
        if m:
            out.append((m.group(1), m.group(2).strip()))
    return out


def body_text(md: str) -> str:
    secs = split_sections(md)
    for key in ("整理后正文", "全文文字稿（ASR）", "全文文字稿（本地 Whisper ASR）", "全文文字稿"):
        if key in secs and secs[key]:
            return secs[key]
    for k, v in secs.items():
        if k.startswith("全文文字稿") or k.startswith("整理后正文"):
            return v
    return ""


def first_sentences(text: str, n: int = 2) -> str:
    compact = re.sub(r"\s+", "", re.sub(r"^#+\s+.*$", "", text, flags=re.M))
    sents = [x for x in re.split(r"[。！？]", compact) if len(x) >= 8]
    picked = []
    for s in sents:
        s = LEAD.sub("", s).strip("，。 ")
        if len(s) < 8:
            continue
        picked.append(s)
        if len(picked) >= n:
            break
    if not picked and sents:
        picked = sents[:n]
    joined = "。".join(picked)
    if joined and not joined.endswith("。"):
        joined += "。"
    return joined[:120] if joined else "本集围绕投资理念展开，细节以全文润色稿为准。"


def occasion(text: str) -> str:
    head = re.sub(r"\s+", "", text)[:400]
    if "孩子" in head or "年轻人" in head:
        return "对着新股民或年轻人补底层逻辑，而不是听完去炒题材。"
    if "群里" in head or "股友" in head:
        return "回应群里或股友的具体问题，把例子收回到可复用的框架。"
    if "周末" in head or "继续跟大家聊" in head or "继续和大家" in head:
        return "例行分享：把最近的行情、公司或对话，收成一套可重复使用的看法。"
    return "把这一期口播收成可检索的判断与章节提要，方便对照全文。"


def pick_source(index: int) -> Path | None:
    pol = sorted(POLISHED.glob(f"{index:03d}_*.md"))
    pol = [p for p in pol if "chapters" not in p.name]
    if pol:
        return pol[0]
    raw = sorted(TRANSCRIPTS.glob(f"{index:03d}_*.md"))
    return raw[0] if raw else None


def render_draft(index: int, src: Path) -> str:
    md = src.read_text(encoding="utf-8")
    meta = parse_meta(split_sections(md).get("_preamble", ""))
    title = meta.get("title") or src.stem
    track_id = meta.get("音频 ID") or ""
    duration = meta.get("时长") or ""
    chapters = parse_chapters(md)
    body = body_text(md)
    one = first_sentences(body, 2)
    claims = []
    for i, (_ts, chap_title) in enumerate(chapters[:8], 1):
        label = re.sub(r"^(开篇：|收束：)", "", chap_title)
        claims.append(f"{i}. {label}")
    if not claims:
        claims = ["1. 对照全文润色稿把握本集主线，结构稿只作导航。"]
    table_rows = []
    if chapters:
        for ts, chap_title in chapters:
            table_rows.append(f"| {ts} | {chap_title} |")
    else:
        table_rows.append("| 00:00 | 见全文润色稿 |")

    lines = [
        f"# {title} · 结构稿",
        "",
        "> **这不是润色稿。** 全文仍以同序号的润色稿为准。本页是理解层：论题、判断和按时间提要。不是逐字，不是投资建议。",
        "",
        f"- 序号：{index:03d}" + (f" · 音频 ID：{track_id}" if track_id else ""),
        f"- 时长：{duration}" if duration else "",
        "",
        "## 一句话",
        "",
        one,
        "",
        "## 他想办成的事",
        "",
        occasion(body),
        "",
        "## 主线判断",
        "",
        *claims,
        "",
        "## 按时间的提要",
        "",
        "| 时间 | 这一段在干什么 |",
        "| --- | --- |",
        *table_rows,
        "",
        "## 限定",
        "",
        "举例不是下单指令。数字、公司名以音频和润色全文为准；结构稿只负责导航和收束。",
        "",
    ]
    return "\n".join([ln for ln in lines if ln is not None]).replace("\n\n\n", "\n\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force-all", action="store_true", help="Also overwrite handcrafted 392")
    args = ap.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    written = 0
    skipped = 0
    for i in range(1, 393):
        if i in SKIP_HANDCRAFTED and not args.force_all:
            existing = list(OUT_DIR.glob(f"{i:03d}_*.md"))
            if existing:
                skipped += 1
                continue
        src = pick_source(i)
        if not src:
            print(f"missing source {i}")
            continue
        text = render_draft(i, src)
        stem = src.stem
        out = OUT_DIR / f"{stem}.md"
        out.write_text(text, encoding="utf-8", newline="\n")
        written += 1
        if written % 50 == 0:
            print(f"wrote {written}")
    print(f"done written={written} skipped_handcrafted={skipped}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Replace synthetic chapter titles for tracks with no official Show Notes."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CONTENT = REPO / "content"
TRANSCRIPTS = CONTENT / "transcripts"
NO_SHOWNOTES = Path(__file__).with_name("no_shownotes.json")

LEAD = re.compile(
    r"^(所以呢?|其实呢?|那么呢?|就是说?|这个|那个|然后呢?|我觉得|我看|大家|"
    r"咱们|今天|继续|跟大家|聊天)+"
)
KEYS = (
    "本质", "规律", "核心", "底层", "第一", "问题", "股权", "分红", "风险",
    "投资", "通胀", "现金", "股东", "估值", "企业", "银行", "国债", "黄金",
    "轮动", "持有", "复利", "护城河", "现金流", "能力圈",
)


def parse_duration(md: str) -> int:
    m = re.search(r"- 时长：(?:(\d+):)?(\d+):(\d+)", md)
    if not m:
        return 0
    h, a, b = m.group(1), m.group(2), m.group(3)
    if h is not None:
        return int(h) * 3600 + int(a) * 60 + int(b)
    return int(a) * 60 + int(b)


def fmt_ts(sec: int) -> str:
    sec = max(0, int(sec))
    mm, ss = divmod(sec, 60)
    if mm >= 60:
        hh, mm = divmod(mm, 60)
        return f"{hh}:{mm:02d}:{ss:02d}"
    return f"{mm:02d}:{ss:02d}"


def extract_body(md: str) -> str:
    m = re.search(r"^## 全文文字稿.*?\n", md, re.M)
    if m:
        body = md[m.end():]
    else:
        m = re.search(r"^## 整理后正文.*?\n", md, re.M)
        body = md[m.end():] if m else md
    body = re.sub(r"^###\s+.*$", "", body, flags=re.M)
    return body.strip()


def pick_body(index: int, transcript_md: str) -> str:
    pol = sorted((CONTENT / "polished").glob(f"{index:03d}_*.md"))
    pol = [p for p in pol if "chapters" not in p.name]
    if pol:
        body = extract_body(pol[0].read_text(encoding="utf-8"))
        if body:
            return body
    return extract_body(transcript_md)


def chapter_count(duration: int, body_len: int) -> int:
    if duration >= 3600 or body_len > 12000:
        n = 12
    elif duration >= 2400 or body_len > 8000:
        n = 10
    elif duration >= 1200 or body_len > 4000:
        n = 8
    else:
        n = 6
    return n


def compress_title(text: str) -> str:
    raw = re.sub(r"\s+", "", text)
    sents = [x for x in re.split(r"[。！？]", raw) if len(re.sub(r"\W+", "", x)) >= 6]
    if not sents:
        sents = [raw]
    chosen = sents[0]
    for s in sents[:8]:
        if any(k in s for k in KEYS):
            chosen = s
            break
    chosen = LEAD.sub("", chosen)
    chosen = re.sub(r"^#+\d{1,2}:\d{2}(?::\d{2})?", "", chosen)
    chosen = re.sub(r"^(就是|说白了|其实)", "", chosen)
    chosen = chosen.strip("，。、；： ")
    if len(chosen) > 22:
        cut = chosen[:22]
        for i in range(len(cut) - 1, 7, -1):
            if cut[i] in "，、的和与":
                cut = cut[:i]
                break
        chosen = cut
    return chosen or "本段要点"


def synthesize(body: str, duration: int) -> list[tuple[str, str]]:
    paras = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
    if not paras:
        paras = [body.strip()] if body.strip() else ["开篇"]
    compact = [re.sub(r"\s+", "", p) for p in paras]
    total = sum(len(x) for x in compact) or 1
    n = min(chapter_count(duration, total), max(4, len(paras)))
    # Split by character mass, not paragraph count, so times track the talk.
    targets = [int(total * i / n) for i in range(n)]
    chapters: list[tuple[str, str]] = []
    used = 0
    p_i = 0
    for i, start_chars in enumerate(targets):
        while p_i < len(paras) - 1 and used + len(compact[p_i]) < start_chars:
            used += len(compact[p_i])
            p_i += 1
        end_p = len(paras) if i == n - 1 else p_i + 1
        # lookahead: take this para plus following until next chapter start
        if i < n - 1:
            nxt = targets[i + 1]
            take = []
            acc = used
            j = p_i
            while j < len(paras) and acc < nxt:
                take.append(paras[j])
                acc += len(compact[j])
                j += 1
            chunk = "".join(take) if take else paras[p_i]
        else:
            chunk = "".join(paras[p_i:])
        ts = 0 if duration <= 0 else int(duration * start_chars / total)
        title = compress_title(chunk)
        if i == 0:
            title = f"开篇：{title}"
        elif i == n - 1:
            title = f"收束：{title}"
        chapters.append((fmt_ts(ts), title))
    # drop duplicate timestamps
    out: list[tuple[str, str]] = []
    seen = set()
    for ts, title in chapters:
        if ts in seen:
            continue
        seen.add(ts)
        out.append((ts, title))
    return out


def strip_chapter_blocks(md: str) -> str:
    out: list[str] = []
    skip = False
    for line in md.splitlines(True):
        if line.startswith("## 章节速览"):
            skip = True
            continue
        if skip and line.startswith("## "):
            skip = False
        if skip:
            continue
        out.append(line)
    return "".join(out)


def inject_chapters(md: str, chapters: list[tuple[str, str]]) -> str:
    md2 = strip_chapter_blocks(md)
    chap = ["## 章节速览", ""] + [f"- {ts} {title}" for ts, title in chapters] + [""]
    insert = "\n".join(chap) + "\n"
    m = re.search(r"^## 全文文字稿", md2, re.M)
    if not m:
        return md2.rstrip() + "\n\n" + insert
    return md2[: m.start()] + insert + md2[m.start():]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    rows = json.loads(NO_SHOWNOTES.read_text(encoding="utf-8"))
    updated = 0
    for row in rows:
        idx = int(row["index"])
        cands = sorted(TRANSCRIPTS.glob(f"{idx:03d}_*.md"))
        if not cands:
            print(f"missing transcript {idx}")
            continue
        path = cands[0]
        md = path.read_text(encoding="utf-8")
        body = pick_body(idx, md)
        chapters = synthesize(body, parse_duration(md))
        new_md = inject_chapters(md, chapters)
        if new_md != md and not args.dry_run:
            path.write_text(new_md, encoding="utf-8", newline="\n")
        updated += 1
        print(f"{idx:03d} n={len(chapters)} {chapters[0][1][:24]}")
    print(f"updated {updated}/{len(rows)}")


if __name__ == "__main__":
    main()

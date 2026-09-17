#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build 结构稿 markdown for every track. Does not overwrite polished transcripts.

Auto drafts are extractive (chapter body → 提要). They are not the hand-written
392 sample and must not copy the 章节目录 twice and call it a 结构稿.
"""

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
HEADING = re.compile(r"^###\s+(\d{1,2}:\d{2}(?::\d{2})?)\s+(.+)$")
LEAD = re.compile(
    r"^(所以呢?|其实呢?|那么呢?|就是说?|这个|那个|然后呢?|我觉得|我看|大家|咱们)+"
)
CLICKBAIT = re.compile(
    r"[！!？?]+$|揭秘|奥秘|秘笈|关键！|你该如何|谁才是"
)
PROMO = re.compile(
    r"(敬请收听|点击收听|不要错过|欢迎收听|揭开.+秘|你是否)"
)
WEAK = re.compile(
    r"(客人|出去玩儿|普通话|麦兄|小把戏|聊天|哎|嗯|那个时候就是有一个)"
)
CLAIMISH = re.compile(
    r"(规律|底层|本质|不要|不能|必须|核心|长期|分红|股东|均值回归|通胀|信用货币|商业模式|护城河|勤奋|认知|虚拟|实业|思维|股权|负复利)"
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


def intro_text(md: str) -> str:
    secs = split_sections(md)
    return secs.get("AI 简介（润色）") or secs.get("AI 简介") or ""


def split_sentences(text: str) -> list[str]:
    compact = re.sub(r"^#+\s+.*$", " ", text, flags=re.M)
    compact = re.sub(r"\s+", "", compact)
    return [x for x in re.split(r"[。！？]", compact) if len(x) >= 8]


def tidy_sentence(s: str) -> str:
    s = LEAD.sub("", s).strip("，。；、 ")
    s = re.sub(r"^[，、]+", "", s)
    return s


def clip(s: str, n: int) -> str:
    s = s.strip()
    if len(s) <= n:
        return s
    cut = s[:n]
    for sep in ("，", "、", "：", "；"):
        pos = cut.rfind(sep)
        if pos >= 12:
            return cut[:pos]
    return cut.rstrip("，、：；")


def chapter_blocks(body: str) -> list[tuple[str, str, str]]:
    """[(time, heading_title, body), ...] from ### 分段."""
    blocks: list[tuple[str, str, str]] = []
    current_ts = ""
    current_title = ""
    buf: list[str] = []
    for line in body.splitlines():
        m = HEADING.match(line.strip())
        if m:
            if current_ts or buf:
                blocks.append((current_ts, current_title, "\n".join(buf).strip()))
            current_ts, current_title = m.group(1), m.group(2).strip()
            buf = []
            continue
        buf.append(line)
    if current_ts or buf:
        blocks.append((current_ts, current_title, "\n".join(buf).strip()))
    return blocks


def title_gist(title: str) -> str:
    title = CLICKBAIT.sub("", title or "").strip("：: ！!？?")
    if "：" in title:
        left, right = title.split("：", 1)
        pick = right.strip() if 6 <= len(right.strip()) <= 28 else (
            right.strip() if len(right.strip()) < len(left.strip()) else left.strip()
        )
        return clip(pick or left, 22)
    return clip(title, 22)


def score_sentence(s: str) -> float:
    n = len(s)
    score = 0.0
    if 14 <= n <= 36:
        score += 4
    elif 10 <= n <= 48:
        score += 2
    else:
        score -= 2
    if CLAIMISH.search(s):
        score += 5
    if WEAK.search(s):
        score -= 6
    if s.count("我") >= 3:
        score -= 3
    if "比如说" in s or "我经常说" in s or "我说" in s:
        score -= 3
    return score


def gist_from_text(text: str, fallback: str, limit: int = 28) -> str:
    ranked: list[tuple[float, str]] = []
    for raw in split_sentences(text)[:14]:
        s = tidy_sentence(raw)
        if len(s) < 10:
            continue
        ranked.append((score_sentence(s), s))
    ranked.sort(key=lambda x: x[0], reverse=True)
    if ranked and ranked[0][0] >= 8:
        return clip(ranked[0][1], limit)
    return title_gist(fallback)


def one_liner(intro: str, body: str, chapters: list[tuple[str, str]]) -> str:
    for src in (intro,):
        if not src:
            continue
        for raw in split_sentences(src)[:8]:
            if PROMO.search(raw):
                continue
            s = tidy_sentence(raw)
            if 12 <= len(s) <= 80:
                return s if s.endswith("。") else s + "。"
            if len(s) > 80:
                return clip(s, 72) + "。"
    ranked: list[tuple[float, str]] = []
    for raw in split_sentences(body)[:40]:
        s = tidy_sentence(raw)
        sc = score_sentence(s)
        if sc >= 8 and 12 <= len(s) <= 48:
            ranked.append((sc, s))
    ranked.sort(key=lambda x: (-x[0], len(x[1])))
    if ranked:
        s = ranked[0][1]
        return s if s.endswith("。") else s + "。"
    if chapters:
        a = title_gist(chapters[0][1])
        b = title_gist(chapters[-1][1])
        if a and b and a != b:
            return f"从“{a}”讲到“{b}”。"
        if a:
            return a + "。"
    return "本集围绕投资理念展开，细节以全文润色稿为准。"


def occasion(text: str) -> str:
    head = re.sub(r"\s+", "", text)[:400]
    if "孩子" in head or "年轻人" in head or "新股民" in head:
        return "对着新股民或年轻人补底层逻辑，而不是听完去炒题材。"
    if "群里" in head or "股友" in head:
        return "回应群里或股友的具体问题，把例子收回到可复用的框架。"
    if "周末" in head or "继续跟大家聊" in head or "继续和大家" in head:
        return "例行分享：把最近的行情、公司或对话，收成一套可重复使用的看法。"
    if "中报" in head or "年报" in head:
        return "借财报或近期数字把商业模式说清楚，例子不是下单指令。"
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
    intro = intro_text(md)
    blocks = chapter_blocks(body)

    by_time = {ts: (heading, text) for ts, heading, text in blocks if ts}
    table_rows: list[str] = []
    claims: list[str] = []
    seen: set[str] = set()

    def add_claim(text: str) -> None:
        key = re.sub(r"\s+", "", text)
        if not text or key in seen:
            return
        seen.add(key)
        claims.append(text)

    # Prefer whole-episode claim-like sentences, then chapter gists.
    whole_ranked: list[tuple[float, str]] = []
    for raw in split_sentences(body)[:120]:
        s = tidy_sentence(raw)
        sc = score_sentence(s)
        if sc >= 8:
            whole_ranked.append((sc, s))
    whole_ranked.sort(key=lambda x: x[0], reverse=True)
    for _sc, s in whole_ranked:
        add_claim(clip(s, 36))
        if len(claims) >= 5:
            break

    if chapters:
        for ts, chap_title in chapters:
            heading, chunk = by_time.get(ts, (chap_title, ""))
            gist = gist_from_text(chunk, chap_title)
            table_rows.append(f"| {ts} | {gist} |")
            if len(claims) < 6:
                add_claim(gist)
    elif blocks:
        for ts, heading, chunk in blocks:
            gist = gist_from_text(chunk, heading)
            stamp = ts or "—"
            table_rows.append(f"| {stamp} | {gist} |")
            add_claim(gist)
    else:
        table_rows.append("| 00:00 | 见全文润色稿 |")

    if not claims:
        for _ts, chap_title in chapters[:6]:
            claims.append(CLICKBAIT.sub("", chap_title).strip("：: ") or chap_title)
    claims = claims[:6]
    claim_lines = [f"{i}. {c}" for i, c in enumerate(claims, 1)]
    if not claim_lines:
        claim_lines = ["1. 对照全文润色稿把握本集主线，结构稿只作导航。"]

    lines = [
        f"# {title} · 结构稿",
        "",
        "> **这不是润色稿。** 全文仍以同序号的润色稿为准。本页是自动抽取的理解层：论题、判断和按时间提要，不是逐字，也不是投资建议。",
        "",
        f"- 序号：{index:03d}" + (f" · 音频 ID：{track_id}" if track_id else ""),
        f"- 时长：{duration}" if duration else "",
        "",
        "## 一句话",
        "",
        one_liner(intro, body, chapters),
        "",
        "## 他想办成的事",
        "",
        occasion(intro + "\n" + body),
        "",
        "## 主线判断",
        "",
        *claim_lines,
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

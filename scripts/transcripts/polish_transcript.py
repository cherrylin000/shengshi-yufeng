#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Polish ASR transcripts: glossary/fillers/repeats, structured sections,
and SmartArt-style flowchart SVGs from chapter outlines.
"""

from __future__ import annotations

import argparse
import html
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CONTENT = REPO / "content"
TRANSCRIPTS_DIR = CONTENT / "transcripts"
POLISHED_DIR = CONTENT / "polished"
DIAGRAMS_DIR = CONTENT / "diagrams"

sys_path_insert = str(Path(__file__).resolve().parent)
import sys

sys.path.insert(0, sys_path_insert)
from normalize_transcripts import (  # noqa: E402
    GLOSSARY_PATH,
    load_glossary,
    normalize_text,
)

CHAPTER_LINE = re.compile(r"^- (\d{1,2}:\d{2}(?::\d{2})?)\s+(.+?)\s*$")
META_LINE = re.compile(r"^- (.+?)：(.+)$")


def split_md_sections(md: str) -> dict[str, str]:
    parts: dict[str, list[str]] = {"_preamble": []}
    current = "_preamble"
    for line in md.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            parts.setdefault(current, [])
            continue
        parts.setdefault(current, []).append(line)
    return {k: "\n".join(v).strip() for k, v in parts.items()}


def parse_chapters(outline_block: str) -> list[tuple[str, str]]:
    chapters: list[tuple[str, str]] = []
    for line in outline_block.splitlines():
        m = CHAPTER_LINE.match(line.strip())
        if m:
            chapters.append((m.group(1), m.group(2).strip()))
    return chapters


def clean_spoken_body(text: str, glossary: list[tuple[str, str]]) -> str:
    text = normalize_text(text, glossary)
    # Drop ASR stub notices
    lines = []
    for ln in text.splitlines():
        s = ln.strip()
        if s.startswith(">") and ("暂未" in s or "不可当作" in s or "Show Notes" in s):
            continue
        lines.append(ln)
    text = "\n".join(lines)

    # Spoken noise / filler phrases (conservative but broader)
    noise = [
        r"这个这个+",
        r"那个那个+",
        r"就是就是+",
        r"然后然后+",
        r"就是说白了[，,]?",
        r"说白了[，,]?",
        r"你比如说[，,]?",
        r"比如说这个[，,]?",
        r"这个呢[，,]?",
        r"那么呢[，,]?",
        r"然后呢[，,]?",
        r"啊[，、]\s*",
        r"哎呀[，、]\s*",
        r"对吧[？?]?",
        r"是不是[？?]?",
        r"大家知道[，,]?",
        r"我跟你讲[，,]?",
        r"你想想[，,]?",
        r"你看吧[，,]?",
        r"怎么说呢[，,]?",
        r"什么意思呢[，,]?",
        r"基本上基本上",
        r"其实其实",
        r"所以所以",
    ]
    for pat in noise:
        text = re.sub(pat, "", text)

    # Common ASR confusions beyond glossary (high-confidence only)
    replacements = [
        ("超股", "炒股"),
        ("正钱", "挣钱"),
        ("发佳", "发家"),
        ("血力", "学历"),
        ("货币金融血", "货币金融学"),
        ("比曾逻辑", "底层逻辑"),
        ("归拿法", "归纳法"),
        ("演谊法", "演绎法"),
        ("凯信图", "K线图"),
        ("金庸行业", "金融行业"),
        ("金庸模型", "金融模型"),
        ("古友", "股友"),
        ("谷友", "股友"),
        ("信答", "信达"),
        ("中心金融资产", "中信金融资产"),
        ("长相电力", "长江电力"),
        ("负负力", "负复利"),
        ("毛货币", "锚货币"),
        ("均治回归", "均值回归"),
        ("军之回归", "均值回归"),
        ("归律", "规律"),
        ("规骂法", "归纳法"),
        ("底层老记", "底层逻辑"),
        ("泡泡马特", "泡泡玛特"),
        ("朝股", "炒股"),
    ]
    for fr, to in replacements:
        text = text.replace(fr, to)

    text = collapse_near_duplicate_sentences(text)
    text = normalize_punctuation(text)
    text = reflow_paragraphs(text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalize_punctuation(text: str) -> str:
    """Fix common ASR punctuation noise and add basic sentence ends."""
    text = text.replace(",", "，").replace(";", "；").replace("?", "？").replace("!", "！")
    text = re.sub(r"[，,]{2,}", "，", text)
    text = re.sub(r"。{2,}", "。", text)
    text = re.sub(r"，+。", "。", text)
    text = re.sub(r"。，", "。", text)
    # Drop dangling commas before newlines
    text = re.sub(r"，\s*\n", "。\n", text)
    # Ensure sentences often end with period when next clause starts with connective
    text = re.sub(
        r"([^\n。！？])\s*(但是|可是|所以|因此|另外|其实|那么|然后|总之)",
        r"\1。\2",
        text,
    )
    # If a long chunk has no period, insert periods around ~60-90 chars at commas
    chunks = []
    for para in re.split(r"\n{2,}", text):
        para = para.strip()
        if not para:
            continue
        if "。" not in para and "！" not in para and "？" not in para and len(para) > 80:
            parts = para.split("，")
            buf = ""
            rebuilt = []
            for part in parts:
                if not buf:
                    buf = part
                elif len(buf) + len(part) < 42:
                    buf += "，" + part
                else:
                    rebuilt.append(buf + "。")
                    buf = part
            if buf:
                rebuilt.append(buf if buf.endswith(("。", "！", "？")) else buf + "。")
            para = "".join(rebuilt)
        chunks.append(para)
    return "\n\n".join(chunks)


def reflow_paragraphs(text: str) -> str:
    """Split long walls of text into readable paragraphs."""
    paras_out: list[str] = []
    for block in re.split(r"\n{2,}", text):
        block = block.strip()
        if not block:
            continue
        # If already short, keep
        if len(re.sub(r"\s+", "", block)) <= 160:
            paras_out.append(block)
            continue
        sentences = re.split(r"(?<=[。！？])", block)
        buf = ""
        for sent in sentences:
            s = sent.strip()
            if not s:
                continue
            if not buf:
                buf = s
            elif len(re.sub(r"\s+", "", buf + s)) <= 120:
                buf += s
            else:
                paras_out.append(buf)
                buf = s
        if buf:
            paras_out.append(buf)
    return "\n\n".join(paras_out)


def collapse_near_duplicate_sentences(text: str) -> str:
    """Remove consecutive sentences that are nearly identical."""
    parts = re.split(r"(?<=[。！？])", text)
    out: list[str] = []
    prev_norm = ""
    for part in parts:
        raw = part.strip()
        if not raw:
            if part:
                out.append(part)
            continue
        norm = re.sub(r"\s+", "", raw)
        if prev_norm and (norm == prev_norm or (len(norm) > 12 and norm in prev_norm)):
            continue
        out.append(part)
        prev_norm = norm
    return "".join(out)


def structure_by_chapters(body: str, chapters: list[tuple[str, str]]) -> str:
    """Wrap body into chapter sections when chapters exist."""
    paras = [p.strip() for p in re.split(r"\n{2,}", body) if p.strip()]
    if not chapters:
        return "\n\n".join(paras)

    blocks: list[str] = ["## 整理后正文", ""]
    if not paras:
        for ts, title in chapters:
            blocks.append(f"### {ts} {title}")
            blocks.append("")
            blocks.append("（本章暂无可用正文）")
            blocks.append("")
        return "\n".join(blocks)

    n = len(chapters)
    # Prefer balanced distribution, but keep at least one paragraph per chapter when possible
    if len(paras) < n:
        for i, (ts, title) in enumerate(chapters):
            blocks.append(f"### {ts} {title}")
            blocks.append("")
            if i < len(paras):
                blocks.append(paras[i])
            else:
                blocks.append("（本章内容见相邻章节上下文）")
            blocks.append("")
        return "\n".join(blocks).strip() + "\n"

    base = len(paras) // n
    rem = len(paras) % n
    cursor = 0
    for i, (ts, title) in enumerate(chapters):
        take = base + (1 if i < rem else 0)
        section = paras[cursor : cursor + take]
        cursor += take
        blocks.append(f"### {ts} {title}")
        blocks.append("")
        blocks.extend(section or ["（本章暂无可用正文）"])
        blocks.append("")
    return "\n".join(blocks).strip() + "\n"


def build_polished_markdown(
    raw_md: str,
    *,
    glossary: list[tuple[str, str]] | None = None,
) -> tuple[str, list[tuple[str, str]]]:
    glossary = glossary if glossary is not None else load_glossary(GLOSSARY_PATH)
    sections = split_md_sections(raw_md)
    preamble = sections.get("_preamble", "")
    intro = sections.get("AI 简介", "")
    outline = sections.get("章节速览", "")
    asr_key = next((k for k in sections if k.startswith("全文文字稿")), "")
    body = sections.get(asr_key, "") if asr_key else ""

    chapters = parse_chapters(outline)
    cleaned_intro = clean_spoken_body(intro, glossary) if intro else ""
    cleaned_body = clean_spoken_body(body, glossary) if body else ""

    lines: list[str] = []
    if preamble:
        # keep title + meta
        lines.append(preamble)
        lines.append("")
    lines.append("> 本篇为自动润色稿：已做术语修正、去口水话/重复，并按章节重排。")
    lines.append("")
    if cleaned_intro:
        lines.extend(["## AI 简介（润色）", "", cleaned_intro, ""])
    lines.append("## 章节目录")
    lines.append("")
    if chapters:
        for i, (ts, title) in enumerate(chapters, 1):
            lines.append(f"{i}. **{ts}** {title}")
    else:
        lines.append("1. （暂无章节）")
    lines.append("")
    if cleaned_body:
        lines.append(structure_by_chapters(cleaned_body, chapters).rstrip())
        lines.append("")
    elif chapters:
        lines.extend(
            [
                "## 要点提纲（无全文时由章节生成）",
                "",
                *[f"- {ts}：{title}" for ts, title in chapters],
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n", chapters


def generate_flowchart_svg(chapters: list[tuple[str, str]], title: str, out_path: Path) -> Path:
    """Generate a vertical SmartArt-like process flowchart SVG."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    items = chapters[:12] or [("00:00", "暂无章节")]
    box_h = 56
    gap = 28
    width = 720
    top = 72
    height = top + len(items) * (box_h + gap) + 40
    # Align with site DESIGN.md Action Blue / ink grayscale
    colors = ["#0066cc", "#0071e3", "#1d1d1f", "#333333", "#7a7a7a"]

    def esc(s: str) -> str:
        return html.escape(s)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<defs>',
        '<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">',
        '<stop offset="0%" stop-color="#ffffff"/>',
        '<stop offset="100%" stop-color="#f5f5f7"/>',
        '</linearGradient>',
        '<filter id="shadow" x="-5%" y="-5%" width="110%" height="120%">',
        '<feDropShadow dx="0" dy="2" stdDeviation="2" flood-opacity="0.12"/>',
        '</filter>',
        '</defs>',
        f'<rect width="100%" height="100%" fill="url(#bg)"/>',
        f'<text x="{width/2}" y="36" text-anchor="middle" font-family="PingFang SC, Noto Sans SC, sans-serif" font-size="20" font-weight="600" fill="#1d1d1f">{esc(title[:36])}</text>',
        f'<text x="{width/2}" y="58" text-anchor="middle" font-family="PingFang SC, Noto Sans SC, sans-serif" font-size="12" fill="#7a7a7a">章节流程 · SmartArt</text>',
    ]
    cx = width / 2
    box_w = 560
    for i, (ts, chap_title) in enumerate(items):
        y = top + i * (box_h + gap)
        x = (width - box_w) / 2
        color = colors[i % len(colors)]
        label = chap_title if len(chap_title) <= 28 else chap_title[:27] + "…"
        parts.append(
            f'<rect x="{x}" y="{y}" width="{box_w}" height="{box_h}" rx="10" fill="#fff" stroke="{color}" stroke-width="2" filter="url(#shadow)"/>'
        )
        parts.append(
            f'<circle cx="{x + 28}" cy="{y + box_h/2}" r="14" fill="{color}"/>'
        )
        parts.append(
            f'<text x="{x + 28}" y="{y + box_h/2 + 5}" text-anchor="middle" font-family="sans-serif" font-size="12" font-weight="700" fill="#fff">{i+1}</text>'
        )
        parts.append(
            f'<text x="{x + 56}" y="{y + 24}" font-family="PingFang SC, Noto Sans SC, sans-serif" font-size="12" fill="#7a7a7a">{esc(ts)}</text>'
        )
        parts.append(
            f'<text x="{x + 56}" y="{y + 44}" font-family="PingFang SC, Noto Sans SC, sans-serif" font-size="15" font-weight="600" fill="#1d1d1f">{esc(label)}</text>'
        )
        if i < len(items) - 1:
            y2 = y + box_h
            parts.append(
                f'<line x1="{cx}" y1="{y2}" x2="{cx}" y2="{y2 + gap}" stroke="{color}" stroke-width="2" marker-end="url(#arrow)"/>'
            )
    # arrow marker
    parts.insert(
        8,
        '<marker id="arrow" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
        '<path d="M 0 0 L 10 5 L 0 10 z" fill="#7a7a7a"/></marker>',
    )
    parts.append("</svg>")
    out_path.write_text("\n".join(parts) + "\n", encoding="utf-8")
    return out_path


def generate_mindmap_svg(chapters: list[tuple[str, str]], title: str, out_path: Path) -> Path:
    """Generate a radial mind-map style SmartArt SVG."""
    import math

    out_path.parent.mkdir(parents=True, exist_ok=True)
    items = chapters[:10] or [("00:00", "暂无章节")]
    w, h = 900, 640
    cx, cy = w / 2, h / 2 + 10
    colors = ["#0066cc", "#0071e3", "#1d1d1f", "#333333", "#7a7a7a"]

    def esc(s: str) -> str:
        return html.escape(s)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
        '<rect width="100%" height="100%" fill="#f5f5f7"/>',
        f'<text x="{cx}" y="28" text-anchor="middle" font-family="PingFang SC, Noto Sans SC, sans-serif" font-size="18" font-weight="600" fill="#1d1d1f">{esc(title[:40])}</text>',
        f'<circle cx="{cx}" cy="{cy}" r="54" fill="#0066cc"/>',
        f'<text x="{cx}" y="{cy + 5}" text-anchor="middle" font-family="PingFang SC, Noto Sans SC, sans-serif" font-size="14" fill="#fff">核心脉络</text>',
    ]
    n = len(items)
    radius = 210
    for i, (ts, chap_title) in enumerate(items):
        ang = -math.pi / 2 + (2 * math.pi * i / n)
        x = cx + radius * math.cos(ang)
        y = cy + radius * math.sin(ang)
        color = colors[i % len(colors)]
        label = chap_title if len(chap_title) <= 16 else chap_title[:15] + "…"
        parts.append(f'<line x1="{cx}" y1="{cy}" x2="{x}" y2="{y}" stroke="{color}" stroke-width="2" opacity="0.55"/>')
        parts.append(f'<rect x="{x - 90}" y="{y - 24}" width="180" height="48" rx="10" fill="#fff" stroke="{color}" stroke-width="2"/>')
        parts.append(
            f'<text x="{x}" y="{y - 4}" text-anchor="middle" font-family="PingFang SC, Noto Sans SC, sans-serif" font-size="11" fill="#7a7a7a">{esc(ts)}</text>'
        )
        parts.append(
            f'<text x="{x}" y="{y + 14}" text-anchor="middle" font-family="PingFang SC, Noto Sans SC, sans-serif" font-size="13" font-weight="600" fill="#1d1d1f">{esc(label)}</text>'
        )
    parts.append("</svg>")
    out_path.write_text("\n".join(parts) + "\n", encoding="utf-8")
    return out_path


def polish_file(src: Path, *, write: bool = True) -> dict:
    raw = src.read_text(encoding="utf-8")
    title_m = re.match(r"^#\s+(.+)$", raw.strip().splitlines()[0] if raw.strip() else "")
    title = title_m.group(1).strip() if title_m else src.stem
    polished, chapters = build_polished_markdown(raw)

    stem = src.stem
    polished_path = POLISHED_DIR / f"{stem}.md"
    flow_path = DIAGRAMS_DIR / f"{stem}_flowchart.svg"
    mind_path = DIAGRAMS_DIR / f"{stem}_mindmap.svg"

    if write:
        POLISHED_DIR.mkdir(parents=True, exist_ok=True)
        # Only keep flowchart SmartArt (mindmap removed: redundant with chapter nav)
        rel_flow = f"../diagrams/{flow_path.name}"
        polished += (
            "\n## 结构图（流程图）\n\n"
            f"![章节流程图]({rel_flow})\n"
        )
        polished_path.write_text(polished, encoding="utf-8", newline="\n")
        generate_flowchart_svg(chapters, title, flow_path)
        if mind_path.is_file():
            mind_path.unlink()

    return {
        "source": str(src),
        "polished": str(polished_path),
        "flowchart": str(flow_path),
        "chapters": len(chapters),
        "chars": len(re.sub(r"\s+", "", polished)),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Polish transcripts and generate SmartArt diagrams")
    ap.add_argument("--file", type=str, required=True, help="Transcript md path")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    src = Path(args.file)
    if not src.is_absolute():
        cand = CONTENT / args.file
        src = cand if cand.is_file() else TRANSCRIPTS_DIR / args.file
    info = polish_file(src, write=not args.dry_run)
    print(info)


if __name__ == "__main__":
    main()

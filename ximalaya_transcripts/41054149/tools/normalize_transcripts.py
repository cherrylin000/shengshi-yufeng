#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Normalize ximalaya ASR markdown: glossary, Chinese year digits, fillers, repeats."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GLOSSARY_PATH = Path(__file__).resolve().parent / "transcript_glossary.tsv"
TRANSCRIPTS_DIR = ROOT / "transcripts"

CN_DIGIT = {**dict(zip("零一二三四五六七八九", "0123456789")), "〇": "0", "○": "0"}

# Skip two-char spoken years that usually mean duration (e.g. 四五年、五六年)
DURATION_DIGRAMS = {
    ("三", "五"),
    ("四", "五"),
    ("五", "六"),
    ("六", "七"),
    ("七", "八"),
}


def load_glossary(path: Path) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.rstrip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        fr, to = parts[0], parts[1]
        if fr == to:
            continue
        pairs.append((fr, to))
    pairs.sort(key=lambda x: len(x[0]), reverse=True)
    return pairs


def apply_glossary(text: str, pairs: list[tuple[str, str]]) -> str:
    for fr, to in pairs:
        text = text.replace(fr, to)
    return text


def _cn_to_int_digits(s: str) -> str:
    return "".join(CN_DIGIT.get(ch, ch) for ch in s)


def normalize_year_phrases(text: str) -> str:
    """Ambiguous / multi-year spoken chunks before generic digit pass."""
    text = text.replace("零五零六", "05、06年")
    text = text.replace("零五、零六", "05、06年")
    # 零零六七年 -> 06、07年 (common ASR for 06-07)
    text = re.sub(r"零零六七年是零七八年", "06、07年是07、08年", text)
    text = re.sub(r"零零六七年", "06、07年", text)
    # 57年，五六年，59年 / 55年，五六年，57年 — middle is 1956 等年份而非时长
    text = re.sub(
        r"(\d{2}年)[，、]五六年[，、](\d{2}年)",
        r"\1、56年、\2",
        text,
    )
    text = re.sub(
        r"不像刚开始五六年他投资",
        "不像刚开始1956年他投资",
        text,
    )
    text = re.sub(
        r"刚开始五六年他投资",
        "刚开始1956年他投资",
        text,
    )
    return text


def normalize_four_digit_cn_years(text: str) -> str:
    """Convert 一九四九年 / 二〇〇七年 style to 1949年 / 2007年."""

    def repl(m: re.Match[str]) -> str:
        digits = _cn_to_int_digits(m.group(0)[:-1])
        if len(digits) != 4 or not digits.isdigit():
            return m.group(0)
        n = int(digits)
        if 1900 <= n <= 2035:
            return f"{n}年"
        return m.group(0)

    # four Chinese digit chars + 年
    return re.sub(
        r"[零一二三四五六七八九〇]{4}年",
        repl,
        text,
    )


def normalize_two_digit_cn_years(text: str) -> str:
    """Convert 零七年 / 一五年 -> 07年 / 15年; skip common duration pairs."""

    def repl(m: re.Match[str]) -> str:
        a, b = m.group(1), m.group(2)
        if (a, b) in DURATION_DIGRAMS:
            return m.group(0)
        return _cn_to_int_digits(a) + _cn_to_int_digits(b) + "年"

    return re.sub(
        r"([零一二三四五六七八九〇])([零一二三四五六七八九〇])年",
        repl,
        text,
    )


def remove_fillers(text: str) -> str:
    """Remove hesitation particles conservative for spoken transcripts."""
    # After sentence end / newline
    text = re.sub(r"([。！？；\n])\s*呃[，、]?\s*", r"\1", text)
    text = re.sub(r"([。！？；\n])\s*嗯[，、]?\s*", r"\1", text)
    text = re.sub(r"([，,])\s*呃[，、]?\s*", r"\1", text)
    text = re.sub(r"([，,])\s*嗯[，、]?\s*", r"\1", text)
    # Line starts (multiline)
    text = re.sub(r"(?m)^(?:呃|嗯)[，、、]\s*", "", text)
    text = re.sub(r"(?m)^\s*呃\s+", "", text)
    text = re.sub(r"(?m)^\s*嗯\s+", "", text)
    # Mid paragraph light cleanup: isolated 呃， / 嗯，
    for _ in range(3):
        n = len(text)
        text = re.sub(r"\s+呃[，、]\s*", " ", text)
        text = re.sub(r"\s+嗯[，、]\s*", " ", text)
        text = re.sub(r"，呃[，、]?", "，", text)
        text = re.sub(r"，嗯[，、]?", "，", text)
        # 紧接在汉字后的「呃，」（如：一点点呃，）
        text = re.sub(r"([\u4e00-\u9fff])呃([，、])", r"\1\2", text)
        # 汉字之间的「呃」（口水插入）
        text = re.sub(r"([\u4e00-\u9fff])呃([\u4e00-\u9fff])", r"\1\2", text)
        if len(text) == n:
            break
    # 句中「…汉字呃。汉字…」吞掉口水停顿
    text = re.sub(
        r"([\u4e00-\u9fff])呃。(?=[\u4e00-\u9fff])",
        r"\1",
        text,
    )
    text = re.sub(r"([\u4e00-\u9fff])呃(\d)", r"\1\2", text)
    text = re.sub(r"([\u4e00-\u9fff])呃(\s*\n)", r"\1\2", text)
    return text


def collapse_repetition(text: str) -> str:
    """Collapse obvious stammers."""
    pairs = [
        (r"(这个){2,}", r"\1"),
        (r"(就是){2,}", r"\1"),
        (r"(那么){2,}", r"\1"),
        (r"(嗯){3,}", "嗯"),
        (r"我我我+", "我"),
        (r"也也也+", "也"),
    ]
    for pat, rep in pairs:
        text = re.sub(pat, rep, text)
    text = re.sub(
        r"理解的[，、]*理解的[，、]*理解的",
        "理解的",
        text,
    )
    text = re.sub(r"理解的[，、]*理解的", "理解的", text)
    return text


def normalize_text(text: str, glossary: list[tuple[str, str]]) -> str:
    text = apply_glossary(text, glossary)
    text = normalize_year_phrases(text)
    text = normalize_four_digit_cn_years(text)
    text = normalize_two_digit_cn_years(text)
    text = remove_fillers(text)
    text = collapse_repetition(text)
    # second pass: fillers may expose new adjacent duplicates
    text = collapse_repetition(text)
    return text


def main() -> None:
    ap = argparse.ArgumentParser(description="Normalize transcript markdown files.")
    ap.add_argument(
        "--file",
        type=str,
        default="",
        help="Single transcript path relative to album or absolute.",
    )
    ap.add_argument("--dry-run", action="store_true", help="Do not write; show stats.")
    ap.add_argument("--verbose", action="store_true", help="Per-file diff summary.")
    args = ap.parse_args()

    glossary = load_glossary(GLOSSARY_PATH)

    if args.file:
        paths = [Path(args.file)]
        if not paths[0].is_absolute():
            cand = ROOT / args.file
            if cand.is_file():
                paths = [cand]
            else:
                paths = [TRANSCRIPTS_DIR / args.file]
    else:
        paths = sorted(TRANSCRIPTS_DIR.glob("*.md"))

    changed = 0
    total_files = 0
    for p in paths:
        if not p.is_file():
            continue
        total_files += 1
        raw = p.read_text(encoding="utf-8")
        new = normalize_text(raw, glossary)
        if new != raw:
            changed += 1
            if args.verbose:
                print(f"[CHANGED] {p.name} ({len(raw)} -> {len(new)} chars)")
        if args.dry_run:
            continue
        if new != raw:
            p.write_text(new, encoding="utf-8", newline="\n")

    print(f"Files: {total_files}, modified: {changed}, dry_run={args.dry_run}")


if __name__ == "__main__":
    main()

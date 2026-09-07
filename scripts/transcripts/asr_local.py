#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Local ASR via faster-whisper (virtualenv)."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def transcribe_audio(
    audio_path: Path,
    *,
    model_size: str = "tiny",
    language: str = "zh",
    device: str = "cpu",
    compute_type: str = "int8",
) -> dict:
    from faster_whisper import WhisperModel

    model = WhisperModel(model_size, device=device, compute_type=compute_type)
    segments_iter, info = model.transcribe(
        str(audio_path),
        language=language,
        vad_filter=True,
        beam_size=1,
    )
    segments: list[dict] = []
    texts: list[str] = []
    for seg in segments_iter:
        text = (seg.text or "").strip()
        if not text:
            continue
        segments.append(
            {
                "start": round(float(seg.start), 2),
                "end": round(float(seg.end), 2),
                "text": text,
            }
        )
        texts.append(text)
    body = "\n\n".join(texts)
    body = re.sub(r"[ \t]+", " ", body)
    return {
        "language": getattr(info, "language", language),
        "duration": getattr(info, "duration", None),
        "segments": segments,
        "text": body.strip(),
        "charCount": len(re.sub(r"\s+", "", body)),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Local ASR with faster-whisper")
    ap.add_argument("audio", type=str)
    ap.add_argument("--model", default="tiny")
    ap.add_argument("--language", default="zh")
    ap.add_argument("--out", type=str, default="", help="Write JSON result path")
    ap.add_argument("--txt-out", type=str, default="", help="Write plain text path")
    args = ap.parse_args()

    audio = Path(args.audio)
    if not audio.is_file():
        raise SystemExit(f"audio not found: {audio}")

    result = transcribe_audio(audio, model_size=args.model, language=args.language)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {out}")
    if args.txt_out:
        txt = Path(args.txt_out)
        txt.parent.mkdir(parents=True, exist_ok=True)
        txt.write_text(result["text"] + "\n", encoding="utf-8")
        print(f"wrote {txt}")
    print(
        json.dumps(
            {
                "chars": result["charCount"],
                "segments": len(result["segments"]),
                "preview": result["text"][:180],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()

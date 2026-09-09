#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Transcribe local audio with faster-whisper (offline, Chinese)."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEFAULT_MODEL = "small"
DEFAULT_DEVICE = "auto"
DEFAULT_COMPUTE = "int8"


def _segments_to_text(segments: list) -> str:
    parts: list[str] = []
    for seg in segments:
        text = (seg.text or "").strip()
        if text:
            parts.append(text)
    body = "\n\n".join(parts)
    return re.sub(r"\n{3,}", "\n\n", body).strip()


def transcribe_file(
    audio_path: Path,
    *,
    model_size: str = DEFAULT_MODEL,
    device: str = DEFAULT_DEVICE,
    compute_type: str = DEFAULT_COMPUTE,
    language: str = "zh",
) -> str:
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise RuntimeError(
            "faster-whisper not installed. Run: pip install faster-whisper"
        ) from e

    if not audio_path.is_file():
        raise FileNotFoundError(audio_path)

    model = WhisperModel(model_size, device=device, compute_type=compute_type)
    segments, _info = model.transcribe(
        str(audio_path),
        language=language,
        vad_filter=True,
        beam_size=5,
    )
    return _segments_to_text(list(segments))


def main() -> None:
    ap = argparse.ArgumentParser(description="Transcribe audio with faster-whisper")
    ap.add_argument("audio", type=Path)
    ap.add_argument("-o", "--output", type=Path, default=None)
    ap.add_argument("--model", default=DEFAULT_MODEL, help="tiny/base/small/medium/large-v3")
    ap.add_argument("--device", default=DEFAULT_DEVICE, help="cpu, cuda, or auto")
    ap.add_argument("--compute-type", default=DEFAULT_COMPUTE, help="int8, float16, …")
    args = ap.parse_args()

    text = transcribe_file(
        args.audio,
        model_size=args.model,
        device=args.device,
        compute_type=args.compute_type,
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(args.output)
    else:
        print(text[:2000])
        if len(text) > 2000:
            print(f"\n… ({len(text)} chars)", file=sys.stderr)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""One-shot: sync transcripts + metadata into data.js (and refresh index.csv meta)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def run(script: str, *args: str) -> None:
    path = REPO / "scripts" / "site" / script
    cmd = [sys.executable, str(path), *args]
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True)


def main() -> None:
    run("sync_data_from_content.py")
    run("sync_track_meta.py", "--skip-fetch")
    print("Done. For fresh publish times from Ximalaya API, also run:")
    print("  python scripts/site/sync_track_meta.py --resume --delay 0.4")


if __name__ == "__main__":
    main()

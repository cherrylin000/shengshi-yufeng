#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Download Ximalaya track audio (encrypted playUrlList + optional xm-sign)."""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from base64 import b64decode
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
STATE_PATH = REPO / "_agent" / "ximalaya_state.json"

WEB_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0"
)

# www2 device substitution + xor tables (from public Ximalaya-Downloader)
_SUB_TABLE = bytes(
    [
        183, 174, 108, 16, 131, 159, 250, 5, 239, 110, 193, 202, 153, 137, 251, 176,
        119, 150, 47, 204, 97, 237, 1, 71, 177, 42, 88, 218, 166, 82, 87, 94, 14, 195,
        69, 127, 215, 240, 225, 197, 238, 142, 123, 44, 219, 50, 190, 29, 181, 186,
        169, 98, 139, 185, 152, 13, 141, 76, 6, 157, 200, 132, 182, 49, 20, 116, 136,
        43, 155, 194, 101, 231, 162, 242, 151, 213, 53, 60, 26, 134, 211, 56, 28, 223,
        107, 161, 199, 15, 229, 61, 96, 41, 66, 158, 254, 21, 165, 253, 103, 89, 3, 168,
        40, 246, 81, 95, 58, 31, 172, 78, 99, 45, 148, 187, 222, 124, 55, 203, 235, 64,
        68, 149, 180, 35, 113, 207, 118, 111, 91, 38, 247, 214, 7, 212, 209, 189, 241,
        18, 115, 173, 25, 236, 121, 249, 75, 57, 216, 10, 175, 112, 234, 164, 70, 206,
        198, 255, 140, 230, 12, 32, 83, 46, 245, 0, 62, 227, 72, 191, 156, 138, 248, 114,
        220, 90, 84, 170, 128, 19, 24, 122, 146, 80, 39, 37, 8, 34, 22, 11, 93, 130, 63,
        154, 244, 160, 144, 79, 23, 133, 92, 54, 102, 210, 65, 67, 27, 196, 201, 106, 143,
        52, 74, 100, 217, 179, 48, 233, 126, 117, 184, 226, 85, 171, 167, 86, 2, 147, 17,
        135, 228, 252, 105, 30, 192, 129, 178, 120, 36, 145, 51, 163, 77, 205, 73, 4, 188,
        125, 232, 33, 243, 109, 224, 104, 208, 221, 59, 9,
    ]
)
_XOR_KEY = bytes(
    [
        204, 53, 135, 197, 39, 73, 58, 160, 79, 24, 12, 83, 180, 250, 101, 60, 206, 30, 10,
        227, 36, 95, 161, 16, 135, 150, 235, 116, 242, 116, 165, 171,
    ]
)


def decrypt_play_url(encrypted_url: str) -> str:
    encrypted_url = encrypted_url.replace("_", "/").replace("-", "+")
    padding = "=" * (-len(encrypted_url) % 4)
    encrypted_data = b64decode(encrypted_url + padding)
    if len(encrypted_data) < 16:
        return encrypted_url
    data = bytearray(encrypted_data[:-16])
    iv = encrypted_data[-16:]
    for i in range(len(data)):
        data[i] = _SUB_TABLE[data[i]]
    for i in range(0, len(data), 16):
        block = data[i : i + 16]
        data[i : i + 16] = bytes(a ^ b for a, b in zip(block, iv))
    for i in range(0, len(data), 32):
        block = data[i : i + 32]
        data[i : i + 32] = bytes(a ^ b for a, b in zip(block, _XOR_KEY))
    return data.decode("utf-8")


def _load_state() -> dict[str, Any]:
    if STATE_PATH.is_file():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _parse_xm_sign(sign: str) -> tuple[str, str] | None:
    if "&&" not in sign:
        return None
    bid, sid = sign.split("&&", 1)
    if bid and sid:
        return bid, sid
    return None


def refresh_xm_sign(cookie: str, track_id: int = 980020064) -> str | None:
    """Capture xm-sign from a headless browser request (optional playwright)."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None

    captured: dict[str, str] = {}

    def on_request(request: Any) -> None:
        sign = request.headers.get("xm-sign") or request.headers.get("Xm-Sign")
        if sign and "&&" in sign:
            captured["sign"] = sign

    cookies: list[dict[str, str]] = []
    for part in cookie.split(";"):
        part = part.strip()
        if "=" not in part:
            continue
        name, value = part.split("=", 1)
        cookies.append(
            {
                "name": name.strip(),
                "value": value.strip(),
                "domain": ".ximalaya.com",
                "path": "/",
            }
        )

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=WEB_UA)
        if cookies:
            try:
                context.add_cookies(cookies)
            except Exception:
                pass
        page = context.new_page()
        page.on("request", on_request)
        page.goto(f"https://www.ximalaya.com/sound/{track_id}", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(4000)
        browser.close()

    sign = captured.get("sign")
    if sign:
        parsed = _parse_xm_sign(sign)
        if parsed:
            state = _load_state()
            state["bid"] = parsed[0]
            state["sid"] = parsed[1]
            state["xm_sign"] = sign
            state["updated_at"] = int(time.time())
            _save_state(state)
    return sign


def get_xm_sign(cookie: str, track_id: int, *, force_refresh: bool = False) -> str | None:
    state = _load_state()
    if not force_refresh and state.get("xm_sign"):
        age = int(time.time()) - int(state.get("updated_at") or 0)
        if age < 3600:
            return str(state["xm_sign"])

    env_sign = os.environ.get("XIMALAYA_XM_SIGN", "").strip()
    if env_sign and "&&" in env_sign:
        return env_sign

    bid = state.get("bid") or os.environ.get("XIMALAYA_BID", "").strip()
    sid = state.get("sid") or os.environ.get("XIMALAYA_SID", "").strip()
    if bid and sid:
        return f"{bid}&&{sid}"

    return refresh_xm_sign(cookie, track_id=track_id)


def _http_json(url: str, headers: dict[str, str], timeout: float = 30) -> dict:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def resolve_play_url(
    track_id: int,
    cookie: str,
    *,
    quality: int = 1,
    _allow_sign_refresh: bool = True,
) -> str:
    """
    Return direct MP3/M4A URL for track_id.
    quality: 0=32k, 1=64k, 2=128k (M4A when available)
    """
    ts = int(time.time() * 1000)
    api = f"https://www.ximalaya.com/mobile-playpage/track/v3/baseInfo/{ts}"
    params = f"device=www2&trackId={track_id}&trackQualityLevel={quality}"
    url = f"{api}?{params}"

    headers = {
        "User-Agent": WEB_UA,
        "Accept": "application/json",
        "Referer": f"https://www.ximalaya.com/sound/{track_id}",
        "Cookie": cookie,
    }

    attempts: list[str | None] = [None]
    sign = get_xm_sign(cookie, track_id)
    if sign:
        attempts.append(sign)

    last_err = ""
    for attempt_sign in attempts:
        h = dict(headers)
        if attempt_sign:
            h["xm-sign"] = attempt_sign
        try:
            payload = _http_json(url, h)
        except urllib.error.HTTPError as e:
            last_err = f"HTTP {e.code}"
            continue
        except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as e:
            last_err = str(e)
            continue

        if payload.get("ret") not in (0, None):
            last_err = payload.get("msg") or str(payload.get("ret"))
            if attempt_sign is None and payload.get("ret") in (927,):
                break
            continue

        track_info = payload.get("trackInfo") or {}
        if track_info.get("isAuthorized") is False:
            raise PermissionError(f"track {track_id} not authorized (login or purchase required)")

        play_list = track_info.get("playUrlList") or []
        if not play_list:
            last_err = "empty playUrlList"
            continue

        prefer = ("M4A_128", "MP3_64", "MP3_32", "AI")
        by_type = {str(x.get("type") or ""): x for x in play_list if isinstance(x, dict)}
        for typ in prefer:
            item = by_type.get(typ)
            if not item:
                continue
            enc = item.get("url")
            if isinstance(enc, str) and enc.strip():
                return decrypt_play_url(enc.strip())

        first = play_list[0]
        enc = first.get("url") if isinstance(first, dict) else None
        if isinstance(enc, str) and enc.strip():
            return decrypt_play_url(enc.strip())

    if _allow_sign_refresh:
        fresh = refresh_xm_sign(cookie, track_id=track_id)
        if fresh:
            return resolve_play_url(
                track_id, cookie, quality=quality, _allow_sign_refresh=False
            )

    raise RuntimeError(f"cannot resolve play URL for track {track_id}: {last_err}")


def download_track(
    track_id: int,
    dest: Path,
    cookie: str,
    *,
    quality: int = 1,
    timeout: float = 120.0,
) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    play_url = resolve_play_url(track_id, cookie, quality=quality)
    req = urllib.request.Request(play_url, headers={"User-Agent": WEB_UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
    dest.write_bytes(data)
    return dest


def main() -> None:
    import argparse
    import sys

    sys.path.insert(0, os.path.dirname(__file__))
    from browser_cookie import ensure_cookie_env  # noqa: E402

    ap = argparse.ArgumentParser(description="Download one Ximalaya track to mp3/m4a")
    ap.add_argument("track_id", type=int)
    ap.add_argument("-o", "--output", type=Path, default=None)
    ap.add_argument("--refresh-sign", action="store_true")
    args = ap.parse_args()

    cookie = ensure_cookie_env()
    if args.refresh_sign:
        refresh_xm_sign(cookie, track_id=args.track_id)

    out = args.output or (REPO / "_agent" / "audio" / f"{args.track_id}.mp3")
    path = download_track(args.track_id, out, cookie)
    print(path)


if __name__ == "__main__":
    main()

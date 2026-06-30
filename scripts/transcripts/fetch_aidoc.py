#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fetch Ximalaya「原文文稿」via anchor-works-web/aiDoc/page.

Requires a logged-in Cookie (env XIMALAYA_COOKIE). Without it the API returns 401.
"""

from __future__ import annotations

import json
import os
import re
import ssl
import urllib.error
import urllib.request
from typing import Any

AIDOC_ENDPOINTS = (
    "https://m.ximalaya.com/anchor-works-web/aiDoc/page?trackId={track_id}",
    "https://www.ximalaya.com/anchor-works-web/aiDoc/page?trackId={track_id}",
)
SHOWNOTES_API = "https://m.ximalaya.com/anchor-works-web/shownotes/page?trackId={track_id}"
MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 iting/9.0.0"
)
WEB_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def get_cookie() -> str | None:
    raw = os.environ.get("XIMALAYA_COOKIE", "").strip()
    return raw or None


def _ssl_context() -> ssl.SSLContext:
    if os.environ.get("XIMALAYA_INSECURE_SSL", "").strip().lower() in ("1", "true", "yes"):
        return ssl._create_unverified_context()
    return ssl.create_default_context()


def _cookie_prefers_web(cookie: str) -> bool:
    c = cookie.lower()
    return "impl=www.ximalaya.com" in c or "tracktype=web" in c or "xm-page-viewid=ximalaya-web" in c


def _request_profiles(track_id: int, cookie: str) -> list[tuple[str, dict[str, str]]]:
    profiles: list[tuple[str, dict[str, str]]] = []
    if _cookie_prefers_web(cookie):
        order = (("web", WEB_UA), ("mobile", MOBILE_UA))
    else:
        order = (("mobile", MOBILE_UA), ("web", WEB_UA))
    for name, ua in order:
        profiles.append(
            (
                f"{name}-www",
                {
                    "User-Agent": ua,
                    "Accept": "application/json, text/plain, */*",
                    "Referer": f"https://www.ximalaya.com/sound/{track_id}",
                    "Cookie": cookie,
                },
            )
        )
        profiles.append(
            (
                f"{name}-m",
                {
                    "User-Agent": ua,
                    "Accept": "application/json, text/plain, */*",
                    "Referer": f"https://m.ximalaya.com/sound/{track_id}",
                    "Cookie": cookie,
                },
            )
        )
    return profiles


def _http_json(url: str, headers: dict[str, str], timeout: float = 30) -> tuple[int, dict | None, str]:
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        try:
            return resp.status, json.loads(raw), raw
        except json.JSONDecodeError:
            return resp.status, None, raw
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(body), body
        except json.JSONDecodeError:
            return e.code, None, body


def fetch_aidoc_payload(track_id: int, cookie: str | None = None) -> dict:
    cookie = cookie or get_cookie()
    if not cookie:
        raise PermissionError("XIMALAYA_COOKIE not set")

    errors: list[str] = []
    for api_tpl in AIDOC_ENDPOINTS:
        url = api_tpl.format(track_id=track_id)
        for profile_name, headers in _request_profiles(track_id, cookie):
            status, payload, raw = _http_json(url, headers)
            if payload is not None:
                ret = payload.get("ret")
                msg = payload.get("msg") or ""
                if status == 200 and ret in (0, None, "0", 200) or payload.get("success"):
                    payload["_source"] = f"{profile_name}:{url}"
                    return payload
                if ret == 50 or "登录" in str(msg):
                    errors.append(f"{profile_name} ret=50 请登录")
                    continue
                if payload.get("data") is not None:
                    payload["_source"] = f"{profile_name}:{url}"
                    return payload
                errors.append(f"{profile_name} ret={ret} msg={msg}")
            else:
                snippet = re.sub(r"\s+", " ", raw)[:120]
                errors.append(f"{profile_name} HTTP {status} non-JSON: {snippet}")

    # Authenticated Show Notes may expose aiDocUrl even when aiDoc/page fails
    shownotes_url = SHOWNOTES_API.format(track_id=track_id)
    for profile_name, headers in _request_profiles(track_id, cookie)[:2]:
        status, payload, _ = _http_json(shownotes_url, headers)
        if not payload:
            continue
        data = payload.get("data") or {}
        ai_doc_url = data.get("aiDocUrl")
        if isinstance(ai_doc_url, str) and ai_doc_url.startswith("http"):
            doc_text = _fetch_doc_url(ai_doc_url, cookie=cookie)
            if doc_text:
                return {
                    "ret": 0,
                    "data": {"docContent": doc_text, "aiDocUrl": ai_doc_url},
                    "_source": f"{profile_name}:shownotes",
                }

    detail = "; ".join(errors[:4])
    raise PermissionError(f"aiDoc unavailable for track {track_id}: {detail}")


def _collect_strings(node: Any, out: list[str]) -> None:
    if isinstance(node, str):
        text = node.strip()
        if text and len(text) > 1:
            out.append(text)
    elif isinstance(node, dict):
        for v in node.values():
            _collect_strings(v, out)
    elif isinstance(node, list):
        for item in node:
            _collect_strings(item, out)


def _pick_longest_text(candidates: list[str]) -> str | None:
    cleaned = [c for c in candidates if len(re.sub(r"\s+", "", c)) >= 80]
    if not cleaned:
        return None
    return max(cleaned, key=len)


def parse_aidoc_text(payload: dict) -> str | None:
    """Extract ASR body from aiDoc/page JSON."""
    if payload.get("success") is False:
        raise ValueError(payload.get("msg") or "aiDoc success=false")
    if payload.get("ret") not in (0, None, "0", 200) and not payload.get("success"):
        if str(payload.get("code")) not in ("200", "0"):
            raise ValueError(payload.get("msg") or "aiDoc API error")

    data = payload.get("data")
    if data is None:
        return None

    if isinstance(data, str) and data.strip():
        return data.strip()

    if not isinstance(data, dict):
        return None

    for key in (
        "docContent",
        "content",
        "text",
        "fullText",
        "asrText",
        "aiDocContent",
        "originalText",
    ):
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()

    doc = data.get("aiDoc") or data.get("doc") or data.get("document")
    if isinstance(doc, dict):
        for key in ("docContent", "content", "text", "fullText"):
            val = doc.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
        url = doc.get("url") or doc.get("docUrl") or doc.get("aiDocUrl")
        if isinstance(url, str) and url.startswith("http"):
            fetched = _fetch_doc_url(url)
            if fetched:
                return fetched

    for key in ("paragraphs", "paragraphList", "sentences", "items", "contents", "docParagraphs"):
        items = data.get(key)
        if isinstance(items, list) and items:
            parts: list[str] = []
            for item in items:
                if isinstance(item, str):
                    parts.append(item.strip())
                elif isinstance(item, dict):
                    for k in ("text", "content", "sentence", "value", "paragraphText"):
                        if isinstance(item.get(k), str) and item[k].strip():
                            parts.append(item[k].strip())
                            break
            body = "\n\n".join(p for p in parts if p)
            if len(re.sub(r"\s+", "", body)) >= 80:
                return body

    url = data.get("aiDocUrl") or data.get("docUrl") or data.get("url")
    if isinstance(url, str) and url.startswith("http") and "ximalaya.com/sound/" not in url:
        fetched = _fetch_doc_url(url)
        if fetched:
            return fetched

    strings: list[str] = []
    _collect_strings(data, strings)
    return _pick_longest_text(strings)


def _fetch_doc_url(url: str, cookie: str | None = None) -> str | None:
    headers: dict[str, str] = {"User-Agent": WEB_UA, "Accept": "*/*"}
    if cookie:
        headers["Cookie"] = cookie
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30, context=_ssl_context()) as resp:
        raw = resp.read().decode("utf-8", errors="replace").strip()
    if not raw:
        return None
    if raw.startswith("{"):
        try:
            return parse_aidoc_text(json.loads(raw))
        except (ValueError, json.JSONDecodeError):
            pass
    if len(re.sub(r"\s+", "", raw)) >= 80:
        return raw
    return None


def fetch_aidoc_text(track_id: int, cookie: str | None = None) -> str | None:
    payload = fetch_aidoc_payload(track_id, cookie=cookie)
    return parse_aidoc_text(payload)


def main() -> None:
    import argparse
    import sys

    ap = argparse.ArgumentParser(description="Fetch Ximalaya aiDoc/原文文稿 for one trackId")
    ap.add_argument("track_id", type=int, nargs="?", default=980020064)
    ap.add_argument("--debug", action="store_true", help="Print API diagnostics, not full text")
    args = ap.parse_args()

    if not get_cookie():
        print("XIMALAYA_COOKIE not set", file=sys.stderr)
        raise SystemExit(1)

    try:
        payload = fetch_aidoc_payload(args.track_id)
    except PermissionError as e:
        print(f"FAIL: {e}", file=sys.stderr)
        raise SystemExit(2) from e

    if args.debug:
        print("source:", payload.get("_source"))
        print("ret:", payload.get("ret"), "msg:", payload.get("msg"))
        data = payload.get("data")
        if isinstance(data, dict):
            print("data keys:", list(data.keys())[:25])
        text = parse_aidoc_text(payload)
        if text:
            print("chars:", len(text))
            print("preview:", text[:200].replace("\n", " "))
            raise SystemExit(0)
        print("parse_aidoc_text returned None")
        print(json.dumps(payload, ensure_ascii=False)[:1500])
        raise SystemExit(2)

    text = parse_aidoc_text(payload)
    if not text:
        print("No text extracted", file=sys.stderr)
        raise SystemExit(2)
    print(text[:2000])
    if len(text) > 2000:
        print(f"\n… ({len(text)} chars total)", file=sys.stderr)


if __name__ == "__main__":
    main()

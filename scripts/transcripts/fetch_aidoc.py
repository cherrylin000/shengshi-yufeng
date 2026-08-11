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


def sanitize_cookie(raw: str) -> str:
    """Normalize pasted Cookie headers for env/Secrets use."""
    text = raw.strip().strip('"').strip("'")
    # Allow pasting the whole "Cookie: a=b; c=d" header line
    if text.lower().startswith("cookie:"):
        text = text.split(":", 1)[1].strip()
    # Secrets / editors sometimes introduce newlines or CR
    text = re.sub(r"[\r\n\t]+", " ", text)
    text = re.sub(r"\s*;\s*", "; ", text)
    text = re.sub(r"\s+", " ", text).strip().strip(";")
    return text


def get_cookie() -> str | None:
    raw = os.environ.get("XIMALAYA_COOKIE", "")
    cleaned = sanitize_cookie(raw)
    return cleaned or None


def cookie_diagnostics(cookie: str | None = None) -> dict[str, Any]:
    """Safe (no secret values) summary of whether Cookie looks logged-in."""
    cookie = cookie or get_cookie() or ""
    pairs = [p.strip() for p in cookie.split(";") if p.strip() and "=" in p]
    names: list[str] = []
    for p in pairs:
        name = p.split("=", 1)[0].strip().strip('"').strip("'")
        if name:
            names.append(name)
    lower_blob = ";".join(names).lower()
    # Real login sessions usually include token-like keys; share/WAF cookies do not.
    login_markers = [
        n
        for n in names
        if "_token" in n.lower()
        or n.lower() in {"login_type", "login_system", "remember_me", "c-oper", "uid", "measurekey"}
        or "xm_portal" in n.lower()
    ]
    share_or_waf = [
        n
        for n in names
        if n.upper().startswith("HWWAF")
        or "cps_promote" in n.lower()
        or n.lower() in {"row_key", "x_xmly_row_key", "h5_channel", "isdistributor", "x_xmly_isdistributor"}
    ]
    return {
        "length": len(cookie),
        "pair_count": len(pairs),
        "has_login_markers": bool(login_markers),
        "login_marker_names": sorted(set(login_markers))[:12],
        "share_or_waf_only": bool(share_or_waf) and not login_markers,
        "has_www_impl": "impl=www.ximalaya.com" in cookie.lower() or "ximalaya-web" in lower_blob,
    }


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
                ok_ret = ret in (0, None, "0", 200) or str(payload.get("code")) in ("0", "200")
                if (status == 200 and ok_ret) or (
                    payload.get("success") is True and payload.get("data") is not None
                ):
                    # Still reject explicit login failures even if success field is weird
                    if ret == 50 or "登录" in str(msg):
                        errors.append(f"{profile_name} ret=50 请登录")
                        continue
                    payload["_source"] = f"{profile_name}:{url}"
                    return payload
                if ret == 50 or "登录" in str(msg):
                    errors.append(f"{profile_name} ret=50 请登录")
                    continue
                if payload.get("data") is not None and ok_ret:
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

    cookie = get_cookie()
    diag = cookie_diagnostics(cookie)
    if args.debug:
        print("cookie_diagnostics:", json.dumps(diag, ensure_ascii=False))
        if diag.get("share_or_waf_only"):
            print(
                "HINT: Cookie looks like WAF/share-only (no login token). "
                "Copy Cookie from a logged-in sound page Network request "
                "that contains *_token / login_type — not from xima.tv share links.",
                file=sys.stderr,
            )

    if not cookie:
        print("XIMALAYA_COOKIE not set", file=sys.stderr)
        raise SystemExit(1)

    try:
        payload = fetch_aidoc_payload(args.track_id, cookie=cookie)
    except PermissionError as e:
        print(f"FAIL: {e}", file=sys.stderr)
        if diag.get("share_or_waf_only") or not diag.get("has_login_markers"):
            print(
                "HINT: Secret likely missing login tokens. "
                "Re-copy Cookie while logged in on www.ximalaya.com/sound/<id>.",
                file=sys.stderr,
            )
        raise SystemExit(2) from e
    except Exception as e:
        print(f"FAIL: unexpected {type(e).__name__}: {e}", file=sys.stderr)
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

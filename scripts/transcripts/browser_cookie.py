#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Read Ximalaya login cookies from the local browser (Windows: Chrome / Edge).

Used by sync_local.py so you do not need to copy Cookie from DevTools or GitHub Secrets.
Keep the browser logged in to www.ximalaya.com; re-login only when this script reports failure.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Iterable

# Reuse diagnostics from fetch_aidoc
sys.path.insert(0, os.path.dirname(__file__))
from fetch_aidoc import cookie_diagnostics, sanitize_cookie  # noqa: E402

XIMALAYA_DOMAINS = (
    ".ximalaya.com",
    "www.ximalaya.com",
    "m.ximalaya.com",
    "ximalaya.com",
)


def _cookie_header_from_pairs(pairs: Iterable[tuple[str, str]]) -> str:
    seen: dict[str, str] = {}
    for name, value in pairs:
        name = (name or "").strip()
        if not name:
            continue
        seen[name] = (value or "").strip()
    return "; ".join(f"{k}={v}" for k, v in seen.items())


def _read_with_rookiepy(domains: tuple[str, ...]) -> str | None:
    try:
        import rookiepy
    except ImportError:
        return None

    pairs: list[tuple[str, str]] = []
    for domain in domains:
        try:
            for c in rookiepy.chromium(domains=[domain]):
                pairs.append((c.get("name", ""), c.get("value", "")))
        except Exception:
            continue
        try:
            for c in rookiepy.edge(domains=[domain]):
                pairs.append((c.get("name", ""), c.get("value", "")))
        except Exception:
            continue
    if not pairs:
        return None
    return _cookie_header_from_pairs(pairs)


def _read_with_browser_cookie3(domains: tuple[str, ...]) -> str | None:
    try:
        import browser_cookie3
    except ImportError:
        return None

    pairs: list[tuple[str, str]] = []
    loaders = (
        getattr(browser_cookie3, "chrome", None),
        getattr(browser_cookie3, "edge", None),
        getattr(browser_cookie3, "chromium", None),
    )
    for loader in loaders:
        if loader is None:
            continue
        try:
            jar = loader(domain_name=".ximalaya.com")
        except Exception:
            continue
        for c in jar:
            pairs.append((c.name, c.value))
    if not pairs:
        return None
    return _cookie_header_from_pairs(pairs)


def read_browser_cookie() -> str | None:
    """Return Cookie header string for ximalaya.com, or None."""
    cookie = _read_with_rookiepy(XIMALAYA_DOMAINS)
    if cookie:
        return sanitize_cookie(cookie)
    cookie = _read_with_browser_cookie3(XIMALAYA_DOMAINS)
    if cookie:
        return sanitize_cookie(cookie)
    return None


def ensure_cookie_env() -> str:
    """Set os.environ['XIMALAYA_COOKIE'] from browser if not already set."""
    existing = sanitize_cookie(os.environ.get("XIMALAYA_COOKIE", ""))
    if existing:
        diag = cookie_diagnostics(existing)
        if diag.get("has_login_markers"):
            return existing

    cookie = read_browser_cookie()
    if not cookie:
        raise RuntimeError(
            "无法从 Chrome/Edge 读取喜马拉雅 Cookie。"
            "请先在浏览器登录 www.ximalaya.com，并安装: pip install rookiepy"
        )
    os.environ["XIMALAYA_COOKIE"] = cookie
    return cookie


def main() -> None:
    ap = argparse.ArgumentParser(description="Read Ximalaya Cookie from local Chrome/Edge")
    ap.add_argument("--json", action="store_true", help="Print diagnostics JSON")
    ap.add_argument("--export", action="store_true", help="Print shell export line")
    ap.add_argument("--check", action="store_true", help="Exit 0 only if login markers present")
    args = ap.parse_args()

    cookie = read_browser_cookie()
    if not cookie:
        print("FAIL: no cookie read from browser", file=sys.stderr)
        print("Install: pip install rookiepy", file=sys.stderr)
        raise SystemExit(1)

    diag = cookie_diagnostics(cookie)
    if args.json:
        print(json.dumps({"cookie_length": len(cookie), **diag}, ensure_ascii=False, indent=2))
    elif args.export:
        # PowerShell: $env:XIMALAYA_COOKIE = '...'
        escaped = cookie.replace("'", "''")
        print(f"$env:XIMALAYA_COOKIE = '{escaped}'")
    else:
        print(f"cookie_length: {len(cookie)}")
        print(f"has_login_markers: {diag.get('has_login_markers')}")
        if diag.get("login_marker_names"):
            print("markers:", ", ".join(diag["login_marker_names"][:8]))

    if args.check and not diag.get("has_login_markers"):
        print("FAIL: cookie missing login tokens (_token / login_type)", file=sys.stderr)
        raise SystemExit(2)

    if not args.check and not diag.get("has_login_markers"):
        print(
            "WARN: cookie may be WAF-only; log in on www.ximalaya.com/sound/<id> and retry",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()

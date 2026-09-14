#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

MAX_INLINE_BYTES = 500 * 1024
ALLOWED_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
UPLOAD_DIR = Path(__file__).resolve().parent / "data" / "uploads"
MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


class StorageError(ValueError):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def local_upload_dir() -> Path:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    return UPLOAD_DIR


def _ext(filename: str) -> str:
    return Path(filename).suffix.lower()


def save_note_image(
    *,
    user_id: int,
    note_id: int,
    filename: str,
    data: bytes,
    content_type: str,
) -> str:
    ext = _ext(filename)
    if ext not in ALLOWED_EXT:
        raise StorageError("仅支持 png/jpg/webp/gif")
    mime = MIME[ext]
    stored_name = f"u{user_id}_n{note_id}{ext}"
    token = (os.environ.get("BLOB_READ_WRITE_TOKEN") or "").strip()
    if token:
        return _put_blob(token, stored_name, data, mime)
    if os.environ.get("VERCEL"):
        if len(data) > MAX_INLINE_BYTES:
            raise StorageError("图片过大，请压缩到 500KB 以内后再试")
        b64 = base64.b64encode(data).decode("ascii")
        return f"data:{mime};base64,{b64}"
    dest = local_upload_dir() / stored_name
    dest.write_bytes(data)
    return stored_name


def _put_blob(token: str, stored_name: str, data: bytes, mime: str) -> str:
    req = urllib.request.Request(
        f"https://blob.vercel-storage.com/{stored_name}",
        data=data,
        method="PUT",
        headers={
            "Authorization": f"Bearer {token}",
            "x-api-version": "7",
            "Content-Type": mime,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:300]
        raise StorageError(f"对象存储失败：{exc.code} {body}") from exc
    url = payload.get("url")
    if not url:
        raise StorageError("对象存储未返回 url")
    return str(url)

# Vercel 同域注册登录与勾画笔记 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在同一 Vercel 域名上跑通注册、登录、已读、浏览记录（每人 50 条）、勾画笔记与脑图上传，数据进 Neon Postgres；本地无 `DATABASE_URL` 时仍用 SQLite。

**Architecture:** 静态文稿继续由 Vercel 直出。`/register`、`/login`、`/logout`、`/notes`、`/api/*`、`/uploads/*` rewrite 到 `api/index.py` 挂载的现有 Flask `app`。`webapp/db.py` 按 `DATABASE_URL` 选择 Postgres 或 SQLite。图片优先 Vercel Blob，否则 ≤500KB 以 data URL 写入 `notes.image_path`；本地仍写 `webapp/data/uploads/`。不迁移本机账号。

**Tech Stack:** Flask 3、Werkzeug、SQLite、psycopg3 binary、Vercel Python Serverless、Neon Postgres、可选 Vercel Blob REST、pytest。

**Spec:** `docs/superpowers/specs/2026-09-11-vercel-auth-notes-design.md`

## Global Constraints

- 同域：公开站域名不变；前端继续 `credentials: 'same-origin'` 调 `/api/*`，不改 API 基址。
- 浏览记录：每人只保留最近 **50** 条（写入时裁剪）。常量名：`HISTORY_KEEP = 50`。
- 本地账号：不导入、不迁移；`webapp/data/` 继续 gitignore。
- Vercel 安装：**不得**把 `faster-whisper` / `yt-dlp` 装进 Serverless；使用 `requirements-web.txt`。
- 不重做勾画 UX，不做微信/短信登录，不改 ASR/周更逻辑（workflow 仅改 pip 文件名若拆分依赖）。
- Session：`HttpOnly` + `SameSite=Lax`；`VERCEL` 环境启用 `SESSION_COOKIE_SECURE`。
- SQL 统一使用 `?` 占位符，Postgres 连接层再换成 `%s`。
- 行对象一律按 `row["column"]` 与 `"column" in row.keys()` 访问（与现 Flask 代码兼容）。

## File map

| 文件 | 职责 |
|------|------|
| `webapp/db.py` | 双后端连接、建表、用户/已读/历史/笔记 CRUD；`HISTORY_KEEP=50` |
| `webapp/storage.py` | 脑图：Blob / data URL / 本地文件 |
| `webapp/vercel_wsgi.py` | 把 Vercel rewrite 后的 PATH_INFO 还原成 Flask 路由 |
| `webapp/app.py` | Session 密钥、懒建表、图片 URL、上传走 storage |
| `api/index.py` | Vercel 入口，导出 Flask `app` |
| `requirements-web.txt` | Vercel/Flask 精简依赖 |
| `vercel.json` | 静态 + 动态分流、函数体积排除 |
| `tests/test_db.py` | SQLite 持久化与 50 条裁剪 |
| `tests/test_storage.py` | 图片策略 |
| `tests/test_vercel_wsgi.py` | PATH_INFO 还原 |
| `tests/test_app.py` | Flask 注册登录笔记 API |
| `README.md` | 线上环境变量与验收 |
| `.github/workflows/sync-ximalaya.yml` | 若拆依赖，仍安装完整 `requirements.txt` |

根目录 `requirements.txt` **保留** whisper/yt-dlp，供周更；Vercel 只用 `requirements-web.txt`。

---

### Task 1: 双后端数据库与浏览记录 50 条

**Files:**
- Create: `tests/test_db.py`
- Modify: `webapp/db.py`（整文件重写为双后端，对外函数名保持不变）

**Interfaces:**
- Consumes: 无
- Produces:
  - `HISTORY_KEEP: int` = `50`
  - `is_postgres() -> bool`
  - `connect(db_path=None)` → 连接对象（有 `execute` / `commit` / `close`；`execute` 返回带 `fetchone`/`fetchall`/`lastrowid`/`rowcount` 的 cursor）
  - `init_db(conn=None) -> None`
  - `create_user(conn, username: str, password_hash: str) -> int`
  - `get_user_by_name(conn, username: str)`
  - `get_user(conn, user_id: int)`
  - `set_read_state(conn, user_id, article_index, *, is_read: bool, track_id: int | None = None) -> None`
  - `get_read_map(conn, user_id: int) -> dict[int, bool]`
  - `add_history(conn, user_id, article_index, *, track_id=None, title="") -> None`（插入后删掉超过 50 的旧记录）
  - `list_history(conn, user_id, limit: int = 50)`
  - `create_note(...) -> int`
  - `list_notes` / `notes_for_article` / `delete_note` / `update_note` / `ensure_notes_image_column`

- [ ] **Step 1: Write the failing tests**

创建 `tests/test_db.py`：

```python
# -*- coding: utf-8 -*-
from pathlib import Path

import pytest

import webapp.db as store


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("VERCEL", raising=False)
    db_file = tmp_path / "app.db"
    monkeypatch.setattr(store, "DB_PATH", db_file)
    c = store.connect(db_file)
    store.init_db(c)
    yield c
    c.close()


def test_create_and_get_user(conn):
    uid = store.create_user(conn, "Alice", "hash")
    row = store.get_user_by_name(conn, "alice")
    assert row is not None
    assert int(row["id"]) == uid
    assert row["username"] == "Alice"


def test_read_state_roundtrip(conn):
    uid = store.create_user(conn, "bob", "hash")
    store.set_read_state(conn, uid, 392, is_read=True, track_id=101)
    mp = store.get_read_map(conn, uid)
    assert mp[392] is True


def test_history_keeps_only_50(conn):
    uid = store.create_user(conn, "carol", "hash")
    for i in range(60):
        store.add_history(conn, uid, article_index=i + 1, title=f"t{i}")
    rows = store.list_history(conn, uid, limit=100)
    assert len(rows) == 50
    assert store.HISTORY_KEEP == 50
    indexes = [int(r["article_index"]) for r in rows]
    assert indexes[0] == 60
    assert indexes[-1] == 11


def test_notes_image_path_column(conn):
    uid = store.create_user(conn, "dan", "hash")
    nid = store.create_note(
        conn, uid, article_index=1, selected_text="一段话", thought="想法"
    )
    assert store.update_note(conn, uid, nid, image_path="https://example.com/a.png")
    note = store.notes_for_article(conn, uid, 1)[0]
    assert note["image_path"] == "https://example.com/a.png"


def test_sql_placeholder_conversion_postgres_style():
    converted = store._for_postgres("SELECT * FROM users WHERE id = ? AND name = ?")
    assert converted == "SELECT * FROM users WHERE id = %s AND name = %s"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pip install pytest flask werkzeug -q
.venv/bin/python -m pytest tests/test_db.py -v
```

Expected: FAIL（`HISTORY_KEEP` 或 `_for_postgres` 不存在，或历史仍是 200 条）。

- [ ] **Step 3: Implement `webapp/db.py`**

用下面实现替换整个 `webapp/db.py`（保留模块职责与现有函数名）：

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Users, reading state, browse history, notes — SQLite or Postgres."""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HISTORY_KEEP = 50
DB_PATH = Path(__file__).resolve().parent / "data" / "app.db"


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def is_postgres() -> bool:
    url = (os.environ.get("DATABASE_URL") or "").strip()
    return url.startswith("postgres://") or url.startswith("postgresql://")


def _for_postgres(sql: str) -> str:
    return sql.replace("?", "%s")


class _Cursor:
    def __init__(self, cur: Any, *, postgres: bool):
        self._cur = cur
        self._postgres = postgres

    def fetchone(self):
        row = self._cur.fetchone()
        return _row(row)

    def fetchall(self):
        return [_row(r) for r in self._cur.fetchall()]

    @property
    def lastrowid(self) -> int | None:
        if self._postgres:
            return None
        return int(self._cur.lastrowid) if self._cur.lastrowid is not None else None

    @property
    def rowcount(self) -> int:
        return int(self._cur.rowcount or 0)


class _Conn:
    def __init__(self, raw: Any, *, postgres: bool):
        self.raw = raw
        self.postgres = postgres

    def execute(self, sql: str, params: tuple | list = ()):
        q = _for_postgres(sql) if self.postgres else sql
        cur = self.raw.execute(q, tuple(params))
        return _Cursor(cur, postgres=self.postgres)

    def commit(self) -> None:
        self.raw.commit()

    def close(self) -> None:
        self.raw.close()


def _row(row: Any):
    if row is None:
        return None
    if isinstance(row, dict):
        return row
    keys = row.keys()
    return {k: row[k] for k in keys}


def connect(db_path: Path | None = None) -> _Conn:
    if is_postgres():
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("psycopg is required when DATABASE_URL is set") from exc
        url = os.environ["DATABASE_URL"].strip()
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://") :]
        raw = psycopg.connect(url, row_factory=dict_row, autocommit=False)
        return _Conn(raw, postgres=True)

    if os.environ.get("VERCEL"):
        raise RuntimeError("DATABASE_URL is required on Vercel")

    path = Path(db_path or DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = sqlite3.connect(str(path), check_same_thread=False)
    raw.row_factory = sqlite3.Row
    raw.execute("PRAGMA foreign_keys = ON")
    return _Conn(raw, postgres=False)


def init_db(conn: _Conn | None = None) -> None:
    own = conn is None
    conn = conn or connect()
    if conn.postgres:
        conn.raw.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
              id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
              username TEXT NOT NULL UNIQUE,
              password_hash TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            CREATE UNIQUE INDEX IF NOT EXISTS users_username_lower ON users (LOWER(username));
            CREATE TABLE IF NOT EXISTS article_state (
              id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
              user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              article_index INTEGER NOT NULL,
              track_id INTEGER,
              is_read INTEGER NOT NULL DEFAULT 0,
              updated_at TEXT NOT NULL,
              UNIQUE(user_id, article_index)
            );
            CREATE TABLE IF NOT EXISTS browse_history (
              id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
              user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              article_index INTEGER NOT NULL,
              track_id INTEGER,
              title TEXT,
              visited_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS notes (
              id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
              user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              article_index INTEGER NOT NULL,
              track_id INTEGER,
              article_title TEXT,
              selected_text TEXT NOT NULL,
              thought TEXT NOT NULL DEFAULT '',
              image_path TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_history_user ON browse_history(user_id, visited_at DESC);
            CREATE INDEX IF NOT EXISTS idx_notes_user ON notes(user_id, updated_at DESC);
            CREATE INDEX IF NOT EXISTS idx_state_user ON article_state(user_id, article_index);
            """
        )
        conn.commit()
    else:
        conn.raw.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              username TEXT NOT NULL UNIQUE COLLATE NOCASE,
              password_hash TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS article_state (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              user_id INTEGER NOT NULL,
              article_index INTEGER NOT NULL,
              track_id INTEGER,
              is_read INTEGER NOT NULL DEFAULT 0,
              updated_at TEXT NOT NULL,
              UNIQUE(user_id, article_index),
              FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS browse_history (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              user_id INTEGER NOT NULL,
              article_index INTEGER NOT NULL,
              track_id INTEGER,
              title TEXT,
              visited_at TEXT NOT NULL,
              FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS notes (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              user_id INTEGER NOT NULL,
              article_index INTEGER NOT NULL,
              track_id INTEGER,
              article_title TEXT,
              selected_text TEXT NOT NULL,
              thought TEXT NOT NULL DEFAULT '',
              image_path TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_history_user ON browse_history(user_id, visited_at DESC);
            CREATE INDEX IF NOT EXISTS idx_notes_user ON notes(user_id, updated_at DESC);
            CREATE INDEX IF NOT EXISTS idx_state_user ON article_state(user_id, article_index);
            """
        )
        conn.commit()
        ensure_notes_image_column(conn)
    if own:
        conn.close()


def _insert_id(conn: _Conn, sql: str, params: tuple) -> int:
    if conn.postgres:
        cur = conn.execute(sql + " RETURNING id", params)
        row = cur.fetchone()
        conn.commit()
        return int(row["id"])
    cur = conn.execute(sql, params)
    conn.commit()
    return int(cur.lastrowid)


def create_user(conn: _Conn, username: str, password_hash: str) -> int:
    return _insert_id(
        conn,
        "INSERT INTO users(username, password_hash, created_at) VALUES (?, ?, ?)",
        (username.strip(), password_hash, utcnow()),
    )


def get_user_by_name(conn: _Conn, username: str):
    return conn.execute(
        "SELECT * FROM users WHERE LOWER(username) = LOWER(?)",
        (username.strip(),),
    ).fetchone()


def get_user(conn: _Conn, user_id: int):
    return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def set_read_state(
    conn: _Conn,
    user_id: int,
    article_index: int,
    *,
    is_read: bool,
    track_id: int | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO article_state(user_id, article_index, track_id, is_read, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(user_id, article_index) DO UPDATE SET
          is_read=excluded.is_read,
          track_id=COALESCE(excluded.track_id, article_state.track_id),
          updated_at=excluded.updated_at
        """,
        (user_id, article_index, track_id, 1 if is_read else 0, utcnow()),
    )
    conn.commit()


def get_read_map(conn: _Conn, user_id: int) -> dict[int, bool]:
    rows = conn.execute(
        "SELECT article_index, is_read FROM article_state WHERE user_id = ?",
        (user_id,),
    ).fetchall()
    return {int(r["article_index"]): bool(r["is_read"]) for r in rows}


def add_history(
    conn: _Conn,
    user_id: int,
    article_index: int,
    *,
    track_id: int | None = None,
    title: str = "",
) -> None:
    conn.execute(
        """
        INSERT INTO browse_history(user_id, article_index, track_id, title, visited_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (user_id, article_index, track_id, title, utcnow()),
    )
    if conn.postgres:
        conn.execute(
            """
            DELETE FROM browse_history WHERE id IN (
              SELECT id FROM browse_history
              WHERE user_id = ?
              ORDER BY visited_at DESC, id DESC
              OFFSET ?
            )
            """,
            (user_id, HISTORY_KEEP),
        )
    else:
        conn.execute(
            """
            DELETE FROM browse_history WHERE id IN (
              SELECT id FROM browse_history
              WHERE user_id = ?
              ORDER BY visited_at DESC, id DESC
              LIMIT -1 OFFSET ?
            )
            """,
            (user_id, HISTORY_KEEP),
        )
    conn.commit()


def list_history(conn: _Conn, user_id: int, limit: int = 50):
    return conn.execute(
        """
        SELECT * FROM browse_history
        WHERE user_id = ?
        ORDER BY visited_at DESC, id DESC
        LIMIT ?
        """,
        (user_id, limit),
    ).fetchall()


def create_note(
    conn: _Conn,
    user_id: int,
    *,
    article_index: int,
    selected_text: str,
    thought: str = "",
    track_id: int | None = None,
    article_title: str = "",
) -> int:
    now = utcnow()
    return _insert_id(
        conn,
        """
        INSERT INTO notes(
          user_id, article_index, track_id, article_title, selected_text, thought, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (user_id, article_index, track_id, article_title, selected_text, thought, now, now),
    )


def list_notes(conn: _Conn, user_id: int):
    ensure_notes_image_column(conn)
    return conn.execute(
        """
        SELECT * FROM notes WHERE user_id = ?
        ORDER BY updated_at DESC, id DESC
        """,
        (user_id,),
    ).fetchall()


def delete_note(conn: _Conn, user_id: int, note_id: int) -> bool:
    cur = conn.execute("DELETE FROM notes WHERE id = ? AND user_id = ?", (note_id, user_id))
    conn.commit()
    return cur.rowcount > 0


def notes_for_article(conn: _Conn, user_id: int, article_index: int):
    ensure_notes_image_column(conn)
    return conn.execute(
        """
        SELECT * FROM notes
        WHERE user_id = ? AND article_index = ?
        ORDER BY id ASC
        """,
        (user_id, article_index),
    ).fetchall()


def ensure_notes_image_column(conn: _Conn) -> None:
    if conn.postgres:
        return
    cols = {r[1] for r in conn.raw.execute("PRAGMA table_info(notes)").fetchall()}
    if "image_path" not in cols:
        conn.execute("ALTER TABLE notes ADD COLUMN image_path TEXT")
        conn.commit()


def update_note(
    conn: _Conn,
    user_id: int,
    note_id: int,
    *,
    selected_text: str | None = None,
    thought: str | None = None,
    image_path: str | None = None,
    clear_image: bool = False,
) -> bool:
    ensure_notes_image_column(conn)
    row = conn.execute(
        "SELECT * FROM notes WHERE id = ? AND user_id = ?",
        (note_id, user_id),
    ).fetchone()
    if not row:
        return False
    new_selected = row["selected_text"] if selected_text is None else selected_text
    new_thought = row["thought"] if thought is None else thought
    if clear_image:
        new_image = None
    elif image_path is not None:
        new_image = image_path
    else:
        new_image = row["image_path"] if "image_path" in row.keys() else None
    conn.execute(
        """
        UPDATE notes
        SET selected_text = ?, thought = ?, image_path = ?, updated_at = ?
        WHERE id = ? AND user_id = ?
        """,
        (new_selected, new_thought, new_image, utcnow(), note_id, user_id),
    )
    conn.commit()
    return True
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_db.py -v
```

Expected: PASS（5 passed）。

- [ ] **Step 5: Commit**

```bash
git add tests/test_db.py webapp/db.py
git commit -m "feat: dual SQLite/Postgres store with 50-item history"
```

---

### Task 2: 脑图存储（Blob / data URL / 本地文件）

**Files:**
- Create: `webapp/storage.py`
- Create: `tests/test_storage.py`

**Interfaces:**
- Consumes: 无
- Produces:
  - `MAX_INLINE_BYTES: int` = `500 * 1024`
  - `ALLOWED_EXT: set[str]` = `{".png", ".jpg", ".jpeg", ".webp", ".gif"}`
  - `class StorageError(ValueError)`，属性 `message: str`
  - `save_note_image(*, user_id: int, note_id: int, filename: str, data: bytes, content_type: str) -> str`
    返回写入 `notes.image_path` 的字符串：https URL、`data:` URL、或本地文件名
  - `local_upload_dir() -> Path`

优先级：**有 `BLOB_READ_WRITE_TOKEN` → Blob**；**否则若 `VERCEL` → data URL（超 500KB 抛 StorageError）**；**否则写本地 uploads**。

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_storage.py
from pathlib import Path

import pytest

from webapp import storage


def test_local_save(tmp_path, monkeypatch):
    monkeypatch.delenv("BLOB_READ_WRITE_TOKEN", raising=False)
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.setattr(storage, "UPLOAD_DIR", tmp_path)
    name = storage.save_note_image(
        user_id=1,
        note_id=2,
        filename="a.PNG",
        data=b"hello",
        content_type="image/png",
    )
    assert name == "u1_n2.png"
    assert (tmp_path / name).read_bytes() == b"hello"


def test_vercel_inline_data_url(monkeypatch):
    monkeypatch.delenv("BLOB_READ_WRITE_TOKEN", raising=False)
    monkeypatch.setenv("VERCEL", "1")
    out = storage.save_note_image(
        user_id=1,
        note_id=3,
        filename="x.jpg",
        data=b"abc",
        content_type="image/jpeg",
    )
    assert out.startswith("data:image/jpeg;base64,")


def test_vercel_inline_too_large(monkeypatch):
    monkeypatch.delenv("BLOB_READ_WRITE_TOKEN", raising=False)
    monkeypatch.setenv("VERCEL", "1")
    with pytest.raises(storage.StorageError) as ei:
        storage.save_note_image(
            user_id=1,
            note_id=4,
            filename="big.png",
            data=b"x" * (storage.MAX_INLINE_BYTES + 1),
            content_type="image/png",
        )
    assert "500" in ei.value.message


def test_reject_bad_ext(monkeypatch, tmp_path):
    monkeypatch.delenv("BLOB_READ_WRITE_TOKEN", raising=False)
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.setattr(storage, "UPLOAD_DIR", tmp_path)
    with pytest.raises(storage.StorageError):
        storage.save_note_image(
            user_id=1,
            note_id=5,
            filename="x.exe",
            data=b"a",
            content_type="application/octet-stream",
        )


def test_blob_put(monkeypatch):
    monkeypatch.setenv("BLOB_READ_WRITE_TOKEN", "tok")

    class FakeResp:
        status = 200

        def read(self):
            return b'{"url":"https://blob.example/u1_n9.png"}'

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=30):
        assert "Bearer tok" in req.get_header("Authorization") or req.headers.get(
            "Authorization"
        ) == "Bearer tok"
        return FakeResp()

    monkeypatch.setattr(storage.urllib.request, "urlopen", fake_urlopen)
    url = storage.save_note_image(
        user_id=1,
        note_id=9,
        filename="z.webp",
        data=b"img",
        content_type="image/webp",
    )
    assert url == "https://blob.example/u1_n9.png"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/test_storage.py -v
```

Expected: FAIL（`webapp.storage` 不存在）。

- [ ] **Step 3: Implement `webapp/storage.py`**

```python
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
```

若运行时 Blob API 路径与文档不一致：以 [Vercel Blob 上传文档](https://vercel.com/docs/storage/vercel-blob/using-blob-sdk) 的 REST `PUT https://blob.vercel-storage.com/{pathname}` 为准；测试里 mock `urlopen`，不打真实网络。

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_storage.py -v
```

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add webapp/storage.py tests/test_storage.py
git commit -m "feat: note image storage for blob, data URL, and local files"
```

---

### Task 3: Flask 会话、懒建表、图片接线

**Files:**
- Modify: `webapp/app.py`
- Create: `webapp/vercel_wsgi.py`
- Create: `tests/test_vercel_wsgi.py`
- Create: `tests/test_app.py`

**Interfaces:**
- Consumes: Task 1 的 `store.*`；Task 2 的 `save_note_image` / `StorageError` / `local_upload_dir`
- Produces:
  - Flask `app`（路由集合不变）
  - `note_image_url(row) -> str | None`
  - `wrap_wsgi(app)` 来自 `webapp/vercel_wsgi.py`
  - 导入时**不**调用 `init_db()`；`get_db()` 第一次取连接时 `init_db(conn)`
  - `SECRET_KEY`：环境变量优先；否则读 `webapp/data/secret.key`；若在 `VERCEL` 上两者都没有则启动失败（清晰报错）；本地可生成并写入 secret.key
  - `SESSION_COOKIE_SECURE` 在 `os.environ.get("VERCEL")` 时为 True
  - `app.wsgi_app = wrap_wsgi(app.wsgi_app)`

- [ ] **Step 1: Write failing WSGI + Flask tests**

`tests/test_vercel_wsgi.py`：

```python
from webapp.vercel_wsgi import restore_path_info


def test_strips_api_index_prefix():
    env = {"PATH_INFO": "/api/index/register", "SCRIPT_NAME": ""}
    restore_path_info(env)
    assert env["PATH_INFO"] == "/register"


def test_strips_api_prefix_for_api_routes():
    env = {"PATH_INFO": "/api/index/api/me", "SCRIPT_NAME": ""}
    restore_path_info(env)
    assert env["PATH_INFO"] == "/api/me"


def test_keeps_normal_path():
    env = {"PATH_INFO": "/login", "SCRIPT_NAME": ""}
    restore_path_info(env)
    assert env["PATH_INFO"] == "/login"
```

`tests/test_app.py`：

```python
import io

import pytest


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.delenv("BLOB_READ_WRITE_TOKEN", raising=False)
    monkeypatch.setenv("SECRET_KEY", "unit-test-secret")
    import webapp.db as store
    import webapp.storage as storage

    monkeypatch.setattr(store, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(storage, "UPLOAD_DIR", tmp_path / "uploads")
    from webapp.app import app

    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_register_login_notes(client):
    assert client.get("/api/me").get_json()["loggedIn"] is False
    rv = client.post(
        "/register",
        data={"username": "u1", "password": "secret1", "password2": "secret1"},
        follow_redirects=False,
    )
    assert rv.status_code in (302, 303)
    me = client.get("/api/me").get_json()
    assert me["loggedIn"] is True
    assert me["username"] == "u1"
    created = client.post(
        "/api/notes",
        json={
            "articleIndex": 392,
            "selectedText": "选中的话",
            "thought": "想法",
            "articleTitle": "20260905",
        },
    )
    assert created.get_json()["ok"] is True
    items = client.get("/api/notes?articleIndex=392").get_json()["items"]
    assert items[0]["selectedText"] == "选中的话"
    client.get("/logout")
    denied = client.get("/api/notes")
    assert denied.status_code == 401


def test_history_cap_via_api(client):
    client.post(
        "/register",
        data={"username": "u2", "password": "secret1", "password2": "secret1"},
    )
    for i in range(55):
        client.post("/api/history", json={"articleIndex": i + 1, "title": f"t{i}"})
    items = client.get("/api/history").get_json()["items"]
    assert len(items) == 50


def test_upload_local_image(client):
    client.post(
        "/register",
        data={"username": "u3", "password": "secret1", "password2": "secret1"},
    )
    nid = client.post(
        "/api/notes",
        json={"articleIndex": 1, "selectedText": "图", "thought": ""},
    ).get_json()["id"]
    data = {"image": (io.BytesIO(b"pngbytes"), "mind.png")}
    rv = client.post(
        f"/api/notes/{nid}/image",
        data=data,
        content_type="multipart/form-data",
    )
    body = rv.get_json()
    assert body["ok"] is True
    assert "/uploads/" in body["imageUrl"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/test_vercel_wsgi.py tests/test_app.py -v
```

Expected: FAIL。

- [ ] **Step 3: Implement `webapp/vercel_wsgi.py`**

```python
# -*- coding: utf-8 -*-
from __future__ import annotations


def restore_path_info(environ: dict) -> None:
    path = environ.get("PATH_INFO") or ""
    prefix = "/api/index"
    if path == prefix:
        environ["PATH_INFO"] = "/"
        environ["SCRIPT_NAME"] = ""
        return
    if path.startswith(prefix + "/"):
        environ["PATH_INFO"] = path[len(prefix) :] or "/"
        environ["SCRIPT_NAME"] = ""


def wrap_wsgi(app):
    def inner(environ, start_response):
        restore_path_info(environ)
        return app(environ, start_response)

    return inner
```

- [ ] **Step 4: Patch `webapp/app.py`**

在现有 `app.py` 上做这些最小改动（不要删路由）：

1. 增加 `import os` 与 `from webapp.storage import ...` 前，保持 `sys.path` 插入后 `import db as store`。为避免包名冲突，storage 用同目录 import：

```python
import storage as media  # noqa: E402
from vercel_wsgi import wrap_wsgi  # noqa: E402
```

2. 密钥与 cookie：

```python
def _resolve_secret_key() -> str:
    env = (os.environ.get("SECRET_KEY") or "").strip()
    if env:
        return env
    key_path = Path(__file__).resolve().parent / "data" / "secret.key"
    if key_path.is_file():
        return key_path.read_text(encoding="utf-8").strip()
    if os.environ.get("VERCEL"):
        raise RuntimeError("SECRET_KEY is required on Vercel")
    key_path.parent.mkdir(parents=True, exist_ok=True)
    generated = secrets.token_hex(24)
    key_path.write_text(generated, encoding="utf-8")
    return generated

app.secret_key = _resolve_secret_key()
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = bool(os.environ.get("VERCEL"))
app.wsgi_app = wrap_wsgi(app.wsgi_app)
```

3. **删除** 模块级 `store.init_db()`。改为：

```python
def get_db():
    if "db" not in g:
        g.db = store.connect()
        store.init_db(g.db)
    return g.db
```

4. 增加：

```python
def note_image_url(row) -> str | None:
    path = row["image_path"] if row and "image_path" in row.keys() else None
    if not path:
        return None
    if path.startswith(("http://", "https://", "data:")):
        return path
    return url_for("uploaded_file", filename=path)
```

把 `api_notes` GET 里构造 `imageUrl` 的逻辑改成 `note_image_url(r)`。

5. `api_note_image` POST：读 `file.read()`，调用 `media.save_note_image(...)`，`StorageError` 返回 400 `{"ok": False, "error": err.message}`；成功则 `store.update_note(..., image_path=saved)`，`imageUrl`：若 `saved` 以 `http`/`data:` 开头则原样返回，否则 `url_for("uploaded_file", filename=saved)`。

6. `uploaded_file` 仍从 `media.local_upload_dir()` 读文件（仅本地文件名场景）。

- [ ] **Step 5: Run tests**

```bash
.venv/bin/python -m pytest tests/test_db.py tests/test_storage.py tests/test_vercel_wsgi.py tests/test_app.py -v
```

Expected: PASS。若 `import storage` 因测试从仓库根运行失败，在 `webapp/app.py` 已有的 `sys.path.insert(0, webapp_dir)` 之后 import，测试改为 `from webapp.app import app` 前确保 `sys.path` 含仓库根；必要时在 `tests/conftest.py` 写入：

```python
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "webapp"))
```

- [ ] **Step 6: Commit**

```bash
git add webapp/app.py webapp/vercel_wsgi.py tests/test_app.py tests/test_vercel_wsgi.py tests/conftest.py
git commit -m "feat: wire Flask session, lazy DB init, and image uploads"
```

---

### Task 4: Vercel 入口、分流与精简依赖

**Files:**
- Create: `api/index.py`
- Create: `requirements-web.txt`
- Modify: `vercel.json`
- Modify: `requirements.txt`（追加 `psycopg[binary]>=3.1,<4`，**不要删除** whisper/yt-dlp）

**Interfaces:**
- Consumes: Flask `app`（`webapp.app:app`）
- Produces: Vercel 可构建的 Python 函数；静态路径不被函数抢走

- [ ] **Step 1: Add `requirements-web.txt`**

```
flask>=3.0,<4
werkzeug>=3.0,<4
psycopg[binary]>=3.1,<4
```

根目录 `requirements.txt` 末尾追加一行 `psycopg[binary]>=3.1,<4`，本地 `webapp/app.py` 与周更 venv 都能 import；周更仍安装 whisper。

- [ ] **Step 2: Add `api/index.py`**

```python
# -*- coding: utf-8 -*-
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "webapp"))

from webapp.app import app  # noqa: E402

# Vercel Python looks for `app`
```

- [ ] **Step 3: Replace `vercel.json`**

```json
{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "framework": null,
  "cleanUrls": true,
  "trailingSlash": false,
  "installCommand": "pip install -r requirements-web.txt",
  "functions": {
    "api/index.py": {
      "maxDuration": 10,
      "excludeFiles": "{content,scripts,.github,docs,tests}/**"
    }
  },
  "rewrites": [
    { "source": "/content/article", "destination": "/content/article.html" },
    { "source": "/static/:path*", "destination": "/webapp/static/:path*" },
    { "source": "/register", "destination": "/api/index" },
    { "source": "/login", "destination": "/api/index" },
    { "source": "/logout", "destination": "/api/index" },
    { "source": "/notes", "destination": "/api/index" },
    { "source": "/uploads/:path*", "destination": "/api/index" },
    { "source": "/api/:path*", "destination": "/api/index" }
  ]
}
```

说明：`/static/auth.css` 映射到仓库内已存在的 `webapp/static/auth.css`（静态，不进函数）。Flask `url_for('static')` 仍是 `/static/auth.css`，线上无需改模板。

- [ ] **Step 4: Sanity-check imports locally**

```bash
.venv/bin/pip install -r requirements-web.txt -q
.venv/bin/python -c "import api.index; print(api.index.app.name)"
.venv/bin/python -m pytest tests -v
```

Expected: 打印 Flask app 名；tests PASS。

- [ ] **Step 5: Commit**

```bash
git add api/index.py requirements-web.txt requirements.txt vercel.json
git commit -m "chore: add Vercel Flask entry, rewrites, and slim web requirements"
```

---

### Task 5: README 与上线清单

**Files:**
- Modify: `README.md`（“账号 / 笔记”一节）
- Modify: `docs/superpowers/specs/2026-09-11-vercel-auth-notes-design.md` 状态行改为“实现计划已写：docs/superpowers/plans/2026-09-14-vercel-auth-notes.md”

**Interfaces:**
- Consumes: 以上全部
- Produces: 用户可按文档配置 Neon / 环境变量

- [ ] **Step 1: Rewrite the 账号 section in README.md**

替换 “### 账号 / 笔记（本地 Web DB）” 为：

```markdown
### 账号 / 笔记（公开站 + 本地）

公开站（Vercel）与文稿同域：<https://shengshi-yufeng.vercel.app/register>

Vercel 项目 `shengshi-yufeng` 需配置环境变量（Settings → Environment Variables，Production + Preview）：

| 变量 | 必需 | 说明 |
|------|------|------|
| `DATABASE_URL` | 是 | Neon 免费 Postgres 连接串（含 `sslmode=require`） |
| `SECRET_KEY` | 是 | 随机长字符串，用于登录 Cookie |
| `BLOB_READ_WRITE_TOKEN` | 否 | 配置后脑图走 Vercel Blob；否则线上仅接受 ≤500KB 图 |

本地开发（SQLite，不连 Neon）：

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-web.txt
.venv/bin/python webapp/app.py
```

- 注册：<http://127.0.0.1:8765/register>
- 我的笔记：<http://127.0.0.1:8765/notes>
- 文稿：<http://127.0.0.1:8765/content/article.html?index=392>

本机旧库可删：`rm -rf webapp/data/app.db`（不向线上迁移）。

周更 / ASR 仍使用：`.venv/bin/pip install -r requirements.txt`。
```

注意：README 里嵌套代码块不要破坏外层 markdown；实现时用缩进代码块或拆成两个 fenced 段。

目录结构一行改为：`webapp/` 注册登录笔记后端（SQLite 本地 / Postgres 线上）。

- [ ] **Step 2: Run unit tests once more**

```bash
.venv/bin/python -m pytest tests -v
```

Expected: PASS。

- [ ] **Step 3: Commit**

```bash
git add README.md docs/superpowers/specs/2026-09-11-vercel-auth-notes-design.md
git commit -m "docs: explain Vercel auth env vars and local SQLite"
```

---

### Task 6: 推送、部署与手工验收（实现者 + 用户环境变量）

**Files:** 无新代码。依赖 Task 4 已 push 的 `main` 或本功能分支合入 `main`。

**Interfaces:**
- Consumes: Vercel 项目 `shengshi-yufeng`（`prj_2Q0f8LGmOd43aaMybJEDQDV3wHd5` / team `team_trIVr6ZbHXXXP585DTmlfm3T`）
- Produces: 生产环境可注册登录

- [ ] **Step 1: 用户配置（实现者可协助检查，不能替用户建 Neon 账号）**

1. 打开 https://console.neon.tech 建免费项目，复制 `DATABASE_URL`。
2. Vercel → `shengshi-yufeng` → Settings → Environment Variables 添加 `DATABASE_URL`、`SECRET_KEY`（`python -c "import secrets; print(secrets.token_hex(32))"`）。
3. 可选：Vercel Storage → Blob → 把 token 设为 `BLOB_READ_WRITE_TOKEN`。
4. 重新部署（push `main` 或 Dashboard Redeploy，让函数读到新变量）。

- [ ] **Step 2: 确认构建成功**

用 Vercel MCP：`list_deployments` / `get_deployment`，状态 `READY`。构建日志中 pip 只装 Flask/psycopg，不得出现 `faster-whisper`。

- [ ] **Step 3: 手工验收（浏览器或 curl）**

正式域名：https://shengshi-yufeng.vercel.app

| 检查 | 期望 |
|------|------|
| `/` | 文稿首页正常 |
| `/register` | 注册页；提交后进 `/notes` |
| `/api/me` 登录后 | `loggedIn: true` |
| 文稿 `content/article.html?index=392` | 可勾选已读、勾画保存 |
| 刷新后再打开 | 笔记仍在 |
| 未登录 `GET /api/notes` | 401 |
| 同一用户写 50+ 条 history | 列表最多 50 |

若部署保护导致 403，用 `get_access_to_vercel_url` 生成临时链接验收。

- [ ] **Step 4: 冷启动说明**

Hobby 上 `/register` 第一次可能 1–3 秒，属预期，不必当故障。

---

## Spec coverage（自检）

| Spec 项 | Task |
|---------|------|
| 同域分流静态 vs Flask | 4 |
| `api/index.py` 挂载 Flask | 4 |
| 本地 SQLite / 线上 Postgres | 1 |
| 表结构 + 自动建表 | 1 |
| 浏览记录 50 | 1、3 |
| `DATABASE_URL` `SECRET_KEY` Blob | 3、5、6 |
| 不迁移本地账号 | 5 |
| `/register` `/login` `/api/*` 行为 | 3 |
| Blob 优先、500KB 降级、本地 uploads | 2、3 |
| Session 标志 | 3 |
| 精简 Vercel 依赖 | 4 |
| 验收 | 6 |
| 不改 UX / 不做短信登录 / 不改 ASR | 全局约束（无对应改动任务） |

## 实现时注意

- Postgres `ON CONFLICT(user_id, article_index)` 需要 UNIQUE 约束，DDL 里已有。
- Neon 连接串若为 `postgres://`，`connect()` 内改成 `postgresql://`。
- 函数 `excludeFiles` 必须排除 `content/**`，否则体积过大。
- 不要提交 `webapp/data/`。
- 合入 `main` 后才会更新正式域名；先在本分支部署 Preview 亦可验收。

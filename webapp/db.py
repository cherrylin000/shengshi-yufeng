#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SQLite persistence for users, reading state, browse history, highlights/notes."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "data" / "app.db"


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection | None = None) -> None:
    own = conn is None
    conn = conn or connect()
    conn.executescript(
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
    if own:
        conn.close()


def create_user(conn: sqlite3.Connection, username: str, password_hash: str) -> int:
    cur = conn.execute(
        "INSERT INTO users(username, password_hash, created_at) VALUES (?, ?, ?)",
        (username.strip(), password_hash, utcnow()),
    )
    conn.commit()
    return int(cur.lastrowid)


def get_user_by_name(conn: sqlite3.Connection, username: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM users WHERE username = ? COLLATE NOCASE", (username.strip(),)
    ).fetchone()


def get_user(conn: sqlite3.Connection, user_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def set_read_state(
    conn: sqlite3.Connection,
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


def get_read_map(conn: sqlite3.Connection, user_id: int) -> dict[int, bool]:
    rows = conn.execute(
        "SELECT article_index, is_read FROM article_state WHERE user_id = ?",
        (user_id,),
    ).fetchall()
    return {int(r["article_index"]): bool(r["is_read"]) for r in rows}


def add_history(
    conn: sqlite3.Connection,
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
    # keep last 200
    conn.execute(
        """
        DELETE FROM browse_history WHERE id IN (
          SELECT id FROM browse_history
          WHERE user_id = ?
          ORDER BY visited_at DESC
          LIMIT -1 OFFSET 200
        )
        """,
        (user_id,),
    )
    conn.commit()


def list_history(conn: sqlite3.Connection, user_id: int, limit: int = 50) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT * FROM browse_history
        WHERE user_id = ?
        ORDER BY visited_at DESC
        LIMIT ?
        """,
        (user_id, limit),
    ).fetchall()


def create_note(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    article_index: int,
    selected_text: str,
    thought: str = "",
    track_id: int | None = None,
    article_title: str = "",
) -> int:
    now = utcnow()
    cur = conn.execute(
        """
        INSERT INTO notes(user_id, article_index, track_id, article_title, selected_text, thought, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (user_id, article_index, track_id, article_title, selected_text, thought, now, now),
    )
    conn.commit()
    return int(cur.lastrowid)


def list_notes(conn: sqlite3.Connection, user_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT * FROM notes WHERE user_id = ?
        ORDER BY updated_at DESC, id DESC
        """,
        (user_id,),
    ).fetchall()


def delete_note(conn: sqlite3.Connection, user_id: int, note_id: int) -> bool:
    cur = conn.execute("DELETE FROM notes WHERE id = ? AND user_id = ?", (note_id, user_id))
    conn.commit()
    return cur.rowcount > 0


def notes_for_article(conn: sqlite3.Connection, user_id: int, article_index: int) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT * FROM notes
        WHERE user_id = ? AND article_index = ?
        ORDER BY id ASC
        """,
        (user_id, article_index),
    ).fetchall()

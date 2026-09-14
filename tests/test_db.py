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

import io

import pytest


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.delenv("BLOB_READ_WRITE_TOKEN", raising=False)
    monkeypatch.setenv("SECRET_KEY", "unit-test-secret")
    import db as store  # noqa: E402 — same module webapp.app uses
    import storage as media  # noqa: E402

    monkeypatch.setattr(store, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(media, "UPLOAD_DIR", tmp_path / "uploads")
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

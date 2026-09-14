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

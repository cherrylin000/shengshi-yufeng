#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
盛世裕丰文稿站 · 用户账号 / 已读状态 / 浏览记录 / 高亮笔记
运行：仓库根目录执行
  .venv/bin/python webapp/app.py
然后打开 http://127.0.0.1:8765/register
"""

from __future__ import annotations

import json
import os
import secrets
import sys
from pathlib import Path

from flask import (
    Flask,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import db as store  # noqa: E402
import storage as media  # noqa: E402
from vercel_wsgi import wrap_wsgi  # noqa: E402

app = Flask(
    __name__,
    template_folder=str(Path(__file__).resolve().parent / "templates"),
    static_folder=str(Path(__file__).resolve().parent / "static"),
)
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


def get_db():
    if "db" not in g:
        g.db = store.connect()
        store.init_db(g.db)
    return g.db


@app.teardown_appcontext
def close_db(_exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    return store.get_user(get_db(), int(uid))


def require_user_api():
    user = current_user()
    if not user:
        return None, (jsonify({"ok": False, "error": "请先登录"}), 401)
    return user, None


def note_image_url(row) -> str | None:
    path = row["image_path"] if row and "image_path" in row.keys() else None
    if not path:
        return None
    if path.startswith(("http://", "https://", "data:")):
        return path
    return url_for("uploaded_file", filename=path)


@app.route("/")
def home():
    return send_from_directory(ROOT, "index.html")


@app.route("/index.html")
def index_html():
    return send_from_directory(ROOT, "index.html")


@app.route("/data-index.js")
def data_index_js():
    return send_from_directory(ROOT, "data-index.js")


@app.route("/content/<path:subpath>")
def content_files(subpath: str):
    return send_from_directory(ROOT / "content", subpath)


@app.route("/register", methods=["GET", "POST"])
def register():
    error = ""
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        password2 = request.form.get("password2") or ""
        if len(username) < 2 or len(username) > 32:
            error = "用户名长度需为 2–32 个字符"
        elif len(password) < 6:
            error = "密码至少 6 位"
        elif password != password2:
            error = "两次输入的密码不一致"
        elif store.get_user_by_name(get_db(), username):
            error = "该用户名已被注册"
        else:
            uid = store.create_user(get_db(), username, generate_password_hash(password))
            session["user_id"] = uid
            session["username"] = username
            return redirect(url_for("notes_page"))
    return render_template("register.html", error=error, user=current_user())


@app.route("/login", methods=["GET", "POST"])
def login():
    error = ""
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        row = store.get_user_by_name(get_db(), username)
        if not row or not check_password_hash(row["password_hash"], password):
            error = "用户名或密码不正确"
        else:
            session["user_id"] = int(row["id"])
            session["username"] = row["username"]
            nxt = request.args.get("next") or url_for("notes_page")
            return redirect(nxt)
    return render_template("login.html", error=error, user=current_user())


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


@app.route("/notes")
def notes_page():
    user = current_user()
    if not user:
        return redirect(url_for("login", next=url_for("notes_page")))
    notes = store.list_notes(get_db(), int(user["id"]))
    history = store.list_history(get_db(), int(user["id"]), limit=30)
    read_map = store.get_read_map(get_db(), int(user["id"]))
    return render_template(
        "notes.html",
        user=user,
        notes=notes,
        history=history,
        read_count=sum(1 for v in read_map.values() if v),
    )


@app.route("/api/me")
def api_me():
    user = current_user()
    if not user:
        return jsonify({"ok": True, "loggedIn": False})
    return jsonify({"ok": True, "loggedIn": True, "username": user["username"], "id": user["id"]})


@app.route("/api/read-state", methods=["GET", "POST"])
def api_read_state():
    user, err = require_user_api()
    if err:
        return err
    conn = get_db()
    if request.method == "GET":
        return jsonify({"ok": True, "states": store.get_read_map(conn, int(user["id"]))})
    data = request.get_json(force=True, silent=True) or {}
    idx = int(data.get("articleIndex") or 0)
    if idx <= 0:
        return jsonify({"ok": False, "error": "缺少 articleIndex"}), 400
    store.set_read_state(
        conn,
        int(user["id"]),
        idx,
        is_read=bool(data.get("isRead")),
        track_id=int(data["trackId"]) if data.get("trackId") else None,
    )
    return jsonify({"ok": True})


@app.route("/api/history", methods=["GET", "POST"])
def api_history():
    user, err = require_user_api()
    if err:
        return err
    conn = get_db()
    if request.method == "GET":
        rows = store.list_history(conn, int(user["id"]))
        return jsonify(
            {
                "ok": True,
                "items": [
                    {
                        "articleIndex": r["article_index"],
                        "trackId": r["track_id"],
                        "title": r["title"],
                        "visitedAt": r["visited_at"],
                    }
                    for r in rows
                ],
            }
        )
    data = request.get_json(force=True, silent=True) or {}
    idx = int(data.get("articleIndex") or 0)
    if idx <= 0:
        return jsonify({"ok": False, "error": "缺少 articleIndex"}), 400
    store.add_history(
        conn,
        int(user["id"]),
        idx,
        track_id=int(data["trackId"]) if data.get("trackId") else None,
        title=str(data.get("title") or ""),
    )
    return jsonify({"ok": True})


@app.route("/api/notes", methods=["GET", "POST"])
def api_notes():
    user, err = require_user_api()
    if err:
        return err
    conn = get_db()
    if request.method == "GET":
        article_index = request.args.get("articleIndex")
        if article_index:
            rows = store.notes_for_article(conn, int(user["id"]), int(article_index))
        else:
            rows = store.list_notes(conn, int(user["id"]))
        return jsonify(
            {
                "ok": True,
                "items": [
                    {
                        "id": r["id"],
                        "articleIndex": r["article_index"],
                        "trackId": r["track_id"],
                        "articleTitle": r["article_title"],
                        "selectedText": r["selected_text"],
                        "thought": r["thought"],
                        "imageUrl": note_image_url(r),
                        "createdAt": r["created_at"],
                        "updatedAt": r["updated_at"],
                    }
                    for r in rows
                ],
            }
        )
    data = request.get_json(force=True, silent=True) or {}
    selected = (data.get("selectedText") or "").strip()
    if not selected:
        return jsonify({"ok": False, "error": "请先选择文字"}), 400
    idx = int(data.get("articleIndex") or 0)
    if idx <= 0:
        return jsonify({"ok": False, "error": "缺少 articleIndex"}), 400
    note_id = store.create_note(
        conn,
        int(user["id"]),
        article_index=idx,
        selected_text=selected,
        thought=str(data.get("thought") or "").strip(),
        track_id=int(data["trackId"]) if data.get("trackId") else None,
        article_title=str(data.get("articleTitle") or ""),
    )
    return jsonify({"ok": True, "id": note_id})


@app.route("/api/notes/<int:note_id>", methods=["PATCH", "DELETE"])
def api_note_item(note_id: int):
    user, err = require_user_api()
    if err:
        return err
    conn = get_db()
    if request.method == "DELETE":
        ok = store.delete_note(conn, int(user["id"]), note_id)
        return jsonify({"ok": ok})
    data = request.get_json(force=True, silent=True) or {}
    ok = store.update_note(
        conn,
        int(user["id"]),
        note_id,
        selected_text=(str(data["selectedText"]).strip() if "selectedText" in data else None),
        thought=(str(data.get("thought") or "") if "thought" in data else None),
    )
    return jsonify({"ok": ok})


@app.route("/api/notes/<int:note_id>/image", methods=["POST", "DELETE"])
def api_note_image(note_id: int):
    user, err = require_user_api()
    if err:
        return err
    conn = get_db()
    if request.method == "DELETE":
        ok = store.update_note(conn, int(user["id"]), note_id, clear_image=True)
        return jsonify({"ok": ok})

    file = request.files.get("image")
    if not file or not file.filename:
        return jsonify({"ok": False, "error": "请选择图片"}), 400
    rows = [r for r in store.list_notes(conn, int(user["id"])) if int(r["id"]) == note_id]
    if not rows:
        return jsonify({"ok": False, "error": "笔记不存在"}), 404
    try:
        saved = media.save_note_image(
            user_id=int(user["id"]),
            note_id=note_id,
            filename=file.filename,
            data=file.read(),
            content_type=file.content_type or "application/octet-stream",
        )
    except media.StorageError as err:
        return jsonify({"ok": False, "error": err.message}), 400
    ok = store.update_note(conn, int(user["id"]), note_id, image_path=saved)
    if saved.startswith(("http://", "https://", "data:")):
        image_url = saved
    else:
        image_url = url_for("uploaded_file", filename=saved)
    return jsonify({"ok": ok, "imageUrl": image_url})


@app.route("/uploads/<path:filename>")
def uploaded_file(filename: str):
    user = current_user()
    if not user:
        return redirect(url_for("login"))
    return send_from_directory(media.local_upload_dir(), filename)


def main():
    host = "0.0.0.0"
    port = 8765
    print(f"Register: http://127.0.0.1:{port}/register")
    print(f"Notes:    http://127.0.0.1:{port}/notes")
    print(f"Articles: http://127.0.0.1:{port}/content/article.html?index=1")
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    main()

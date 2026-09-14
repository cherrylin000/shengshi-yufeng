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

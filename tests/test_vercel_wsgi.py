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

import pytest
from fastapi.testclient import TestClient

import webapp.app as web
from webapp import auth


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "correct horse battery")
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.setattr(web, "LOGIN_FAIL_DELAY", 0)
    return TestClient(web.app)


def test_pages_redirect_to_login(client):
    res = client.get("/", follow_redirects=False)
    assert res.status_code == 303 and res.headers["location"] == "/login"


def test_api_requires_session(client):
    assert client.get("/api/config").status_code == 401
    assert client.post("/api/parse", json={"text": "naples"}).status_code == 401


def test_login_assets_stay_public(client):
    for path in ("/login", "/static/login.js", "/static/js/api.js", "/static/styles.css",
                 "/manifest.webmanifest", "/sw.js", "/static/icons/icon-192.png"):
        assert client.get(path).status_code == 200, path
    assert client.get("/static/js/main.js", follow_redirects=False).status_code == 303


def test_wrong_password_rejected(client):
    res = client.post("/api/login", json={"password": "nope"})
    assert res.status_code == 401
    assert auth.COOKIE not in res.cookies


def test_login_grants_access_then_logout(client):
    res = client.post("/api/login", json={"password": "correct horse battery"})
    assert res.status_code == 200
    assert client.get("/api/config").json()["auth"] is True
    client.post("/api/logout")
    client.cookies.clear()
    assert client.get("/api/config").status_code == 401


def test_forged_or_expired_tokens(client):
    client.cookies.set(auth.COOKIE, "9999999999.deadbeef")
    assert client.get("/api/config").status_code == 401
    expired = auth.make_token("correct horse battery", now=0)
    assert not auth.valid_token(expired, "correct horse battery")
    assert not auth.valid_token("pas-un-token", "x")
    assert not auth.valid_token(auth.make_token("autre"), "correct horse battery")


def test_vercel_without_password_is_closed(monkeypatch):
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    monkeypatch.setenv("VERCEL", "1")
    res = TestClient(web.app).get("/")
    assert res.status_code == 503 and "APP_PASSWORD" in res.text


def test_vercel_rejects_short_password(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "court")
    monkeypatch.setenv("VERCEL", "1")
    res = TestClient(web.app).get("/login")
    assert res.status_code == 503 and "trop court" in res.text


def test_vercel_with_strong_password_serves_login(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "une longue phrase de passe")
    monkeypatch.setenv("VERCEL", "1")
    client = TestClient(web.app)
    assert client.get("/login").status_code == 200
    assert client.get("/api/config").status_code == 401


def test_session_secret_rotation_logs_everyone_out(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "a")
    token = auth.make_token("pw-pw-pw-pw-pw")
    assert auth.valid_token(token, "pw-pw-pw-pw-pw")
    monkeypatch.setenv("SESSION_SECRET", "b")
    assert not auth.valid_token(token, "pw-pw-pw-pw-pw")


def test_signing_key_is_not_the_raw_password():
    import hashlib
    import hmac as _hmac
    token = auth.make_token("pw-pw-pw-pw-pw", now=1000)
    expires = token.split(".")[0]
    naive = _hmac.new(b"pw-pw-pw-pw-pw", f"agent-vols:{expires}".encode(), hashlib.sha256).hexdigest()
    assert token.split(".")[1] != naive


def test_only_listed_static_files_are_public():
    assert auth.is_public("/static/login.js")
    assert not auth.is_public("/static/login-debug.js")
    assert not auth.is_public("/static/js/main.js")


def test_local_without_password_is_open(monkeypatch):
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    monkeypatch.delenv("VERCEL", raising=False)
    assert TestClient(web.app).get("/api/config").json()["auth"] is False

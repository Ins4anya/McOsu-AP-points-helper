"""Tests for mcsu_bot.server_client ranked functions (httpx mocked)."""
from __future__ import annotations

import httpx
import pytest

import mcsu_bot.server_client as sc


class FakeResp:
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        return self._payload or {}


def _auth(server_url="http://server", token="tok"):
    return {"server_url": server_url, "token": token}


def test_ranked_request_success(monkeypatch):
    monkeypatch.setattr(sc, "_load_token", lambda: _auth())

    def fake_request(method, url, **kw):
        return FakeResp(200, {"elo": 100, "tier": "Базовый"})

    monkeypatch.setattr(sc.httpx, "request", fake_request)
    ok, data = sc.get_ranked("http://server")
    assert ok is True
    assert data == {"elo": 100, "tier": "Базовый"}


def test_ranked_error_texts(monkeypatch):
    monkeypatch.setattr(sc, "_load_token", lambda: _auth())
    cases = {
        503: "Нет подходящих карт в этом диапазоне",
        429: "Лимит рероллов на сегодня исчерпан",
        409: "Нет активного задания",
    }
    for code, expected in cases.items():
        def fake_request(method, url, _code=code, **kw):
            return FakeResp(_code, {"detail": "x"})

        monkeypatch.setattr(sc.httpx, "request", fake_request)
        ok, msg = sc.ranked_new("http://server")
        assert ok is False
        assert msg == expected


def test_ranked_401_clears_token(monkeypatch):
    monkeypatch.setattr(sc, "_load_token", lambda: _auth())
    cleared = []
    monkeypatch.setattr(sc, "_clear_token", lambda: cleared.append(1))

    def fake_request(method, url, **kw):
        return FakeResp(401)

    monkeypatch.setattr(sc.httpx, "request", fake_request)
    ok, msg = sc.get_ranked("http://server")
    assert ok is False
    assert msg == "Token expired — re-login required"
    assert cleared == [1]


def test_ranked_not_authenticated(monkeypatch):
    monkeypatch.setattr(sc, "_load_token", lambda: _auth(server_url="http://other"))
    ok, msg = sc.get_ranked("http://server")
    assert ok is False
    assert msg == "Not authenticated to this server"


def test_ranked_timeout(monkeypatch):
    monkeypatch.setattr(sc, "_load_token", lambda: _auth())

    def fake_request(method, url, **kw):
        raise httpx.TimeoutException("timeout")

    monkeypatch.setattr(sc.httpx, "request", fake_request)
    ok, msg = sc.get_ranked("http://server")
    assert ok is False
    assert msg == "Server timeout"


def test_ranked_connect_error(monkeypatch):
    monkeypatch.setattr(sc, "_load_token", lambda: _auth())

    def fake_request(method, url, **kw):
        raise httpx.ConnectError("unreachable")

    monkeypatch.setattr(sc.httpx, "request", fake_request)
    ok, msg = sc.get_ranked("http://server")
    assert ok is False
    assert msg == "Cannot connect to server"


def test_ranked_history_passes_params(monkeypatch):
    monkeypatch.setattr(sc, "_load_token", lambda: _auth())
    captured = {}

    def fake_request(method, url, **kw):
        captured["method"] = method
        captured["params"] = kw.get("params")
        return FakeResp(200, [])

    monkeypatch.setattr(sc.httpx, "request", fake_request)
    sc.get_ranked_history("http://server", limit=5, offset=2)
    assert captured["method"] == "GET"
    assert captured["params"] == {"limit": 5, "offset": 2}

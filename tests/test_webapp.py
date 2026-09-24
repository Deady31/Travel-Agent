import json
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import webapp.app as web
from agent_vols.quota import SerpApiQuota
from agent_vols.search import run_search

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "serpapi_tls_nap.json").read_text(encoding="utf-8"))


@pytest.fixture
def client(monkeypatch, tmp_path):
    quota = SerpApiQuota(tmp_path / "q.json", limit=100)

    def fake_live(key, q, *args):
        q.consume()
        return FIXTURE

    def offline_search(params, **kw):
        return run_search(params, **{**kw, "fetch_live": fake_live, "tp_token": ""})

    monkeypatch.setattr(web, "QUOTA", quota)
    monkeypatch.setattr(web, "SERPAPI_KEY", "secret-xyz")
    monkeypatch.setattr(web, "run_search", offline_search)
    web._offers.clear()
    return TestClient(web.app)


def body(**kw):
    start = date.today() + timedelta(days=20)
    base = {"destination_iata": ["NAP"], "origins": ["TLS", "BCN"], "depart_from": start.isoformat(),
            "depart_to": (start + timedelta(days=7)).isoformat(), "stay_min": 4, "stay_max": 5, "budget_eur": 150}
    return {**base, **kw}


def test_index_and_static(client):
    assert "Départs" in client.get("/").text
    assert client.get("/static/js/main.js").status_code == 200


def test_config(client):
    data = client.get("/api/config").json()
    assert data["quota_remaining"] == 100
    assert "TLS" in data["origins"]
    assert "secret-xyz" not in json.dumps(data)  # la clé n'est jamais renvoyée


def test_parse(client):
    data = client.post("/api/parse", json={"text": "naples fin oct 4-5j 150€"}).json()
    assert data["destination_iata"] == ["NAP"]
    assert data["budget_eur"] == 150


def test_parse_rejects_oversized_input(client):
    assert client.post("/api/parse", json={"text": "x" * 301}).status_code == 422


def test_search_then_rank(client):
    res = client.post("/api/search", json=body())
    assert res.status_code == 200
    data = res.json()
    assert len(data["offers"]) == 9
    assert data["quota_remaining"] == 98
    assert "offers_objects" not in data
    ids = [o["id"] for o in data["offers"] if o["stops"] <= 1]
    ranked = client.post("/api/rank", json={"offer_ids": ids, "budget_eur": 600}).json()
    assert ranked["within_budget"] is True
    assert ranked["cheapest"]["price_eur"] == min(o["price_eur"] for o in data["offers"] if o["stops"] <= 1)


@pytest.mark.parametrize("override", [
    {"destination_iata": ["naples"]},
    {"origins": ["XXX"]},
    {"stay_min": 0},
    {"adults": 12},
    {"bag": "piano"},
    {"depart_from": "2020-01-01", "depart_to": "2020-01-05"},
])
def test_search_rejects_bad_input(client, override):
    assert client.post("/api/search", json=body(**override)).status_code in (400, 422)


def test_rank_unknown_ids(client):
    assert client.post("/api/rank", json={"offer_ids": ["nope"]}).status_code == 404


def test_raw_log_scrubs_secrets(monkeypatch, tmp_path):
    monkeypatch.setattr(web, "LOG_DIR", tmp_path)
    monkeypatch.setattr(web, "SERPAPI_KEY", "secret-xyz")
    monkeypatch.setattr(web, "TRAVELPAYOUTS_TOKEN", "tok-abc")
    web._log_raw({"echo": "secret-xyz tok-abc", "price": 155})
    text = next(tmp_path.glob("*.jsonl")).read_text(encoding="utf-8")
    assert "secret-xyz" not in text and "tok-abc" not in text and "155" in text


def test_demo_mode_needs_no_key(client, monkeypatch):
    monkeypatch.setattr(web, "SERPAPI_KEY", "")
    monkeypatch.setattr(web, "DEMO_MODE", True)
    data = client.post("/api/search", json=body()).json()
    assert len(data["offers"]) == 9
    assert data["warnings"][0].startswith("Mode démo")


def test_search_without_key(client, monkeypatch):
    monkeypatch.setattr(web, "SERPAPI_KEY", "")
    assert client.post("/api/search", json=body()).status_code == 400

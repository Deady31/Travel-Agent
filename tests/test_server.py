import json
from pathlib import Path

import pytest

import server
from agent_vols.quota import SerpApiQuota

FIXTURE = Path(__file__).parent / "fixtures" / "serpapi_tls_nap.json"


@pytest.fixture
def offline(monkeypatch, tmp_path):
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    quota = SerpApiQuota(tmp_path / "q.json", limit=100)

    def fake_fetch(api_key, q, *args, **kwargs):
        q.consume()
        return raw

    monkeypatch.setattr(server, "fetch_serpapi", fake_fetch)
    monkeypatch.setattr(server, "QUOTA", quota)
    monkeypatch.setattr(server, "SERPAPI_KEY", "test-key")
    monkeypatch.setattr(server, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(server, "_check_dates", lambda *a: None)
    server._offers.clear()
    return raw


def test_search_then_rank_end_to_end(offline):
    res = server.search_live_flights("tls", "NAP", "2026-10-28", "2026-11-01")
    assert len(res["offers"]) == 9
    assert res["serpapi_quota_remaining"] == 99
    assert res["price_insights"]["price_level"] == "high"

    ranked = server.rank_flights([o["id"] for o in res["offers"]], budget_max_eur=150)
    assert ranked["within_budget"] is False
    raw_prices = {f["price"] for f in offline["best_flights"] + offline["other_flights"]}
    for key in ("cheapest", "best_balance", "most_comfortable"):
        assert ranked[key]["price_eur"] in raw_prices
    assert ranked["cheapest"]["price_eur"] == 552


def test_rank_rejects_unknown_ids(offline):
    with pytest.raises(ValueError, match="inconnues"):
        server.rank_flights(["invente123"])


@pytest.mark.parametrize("origin,dest", [("TOULOUSE", "NAP"), ("TL", "NAP"), ("TLS", "N4P")])
def test_invalid_iata_rejected(offline, origin, dest):
    with pytest.raises(ValueError):
        server.search_live_flights(origin, dest, "2026-10-28", "2026-11-01")


def test_date_validation(monkeypatch):
    with pytest.raises(ValueError, match="passé"):
        server._check_dates("2020-01-01", "2020-01-05")
    with pytest.raises(ValueError, match="après"):
        server._check_dates("2099-01-05", "2099-01-01")
    with pytest.raises(ValueError, match="format"):
        server._check_dates("28/10/2026", "2026-11-01")


def test_logs_never_contain_key(offline, tmp_path):
    offline["search_metadata"]["leak"] = "test-key"
    server.search_live_flights("TLS", "NAP", "2026-10-28", "2026-11-01")
    log = next((tmp_path / "logs").glob("*.jsonl")).read_text(encoding="utf-8")
    assert "test-key" not in log

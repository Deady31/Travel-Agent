import json
from datetime import date
from pathlib import Path

import pytest
import requests

from agent_vols.bags import bag_info, bag_warning
from agent_vols.quota import SerpApiQuota
from agent_vols.search import SearchParams, choose_date_pairs, run_search
from agent_vols.travelpayouts_provider import CacheHint, parse_hints

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "serpapi_tls_nap.json").read_text(encoding="utf-8"))
TODAY = date(2026, 9, 24)


def params(**kw):
    base = dict(destination_iata=("NAP",), origins=("TLS", "BCN"), depart_from=date(2026, 10, 20),
                depart_to=date(2026, 10, 31), stay_min=4, stay_max=5, budget_eur=150)
    return SearchParams(**{**base, **kw})


def hint(out, ret, price):
    return CacheHint("TLS", "NAP", out, ret, price, "FR", 0, "")


# --- choix des dates -------------------------------------------------------

def test_cache_hints_drive_date_choice():
    hints = [hint("2026-10-27", "2026-10-31", 80), hint("2026-10-21", "2026-10-25", 90)]
    pairs = choose_date_pairs(params(), hints, 2)
    assert pairs == [(date(2026, 10, 27), date(2026, 10, 31)), (date(2026, 10, 21), date(2026, 10, 25))]


def test_heuristic_without_cache_prefers_midweek_and_distinct_days():
    pairs = choose_date_pairs(params(), [], 2)
    assert len(pairs) == 2
    assert pairs[0][0] != pairs[1][0]
    assert all(p[0].weekday() in (1, 2) for p in pairs)
    assert all(4 <= (r - o).days <= 5 for o, r in pairs)


def test_duplicate_hints_are_merged():
    hints = [hint("2026-10-27", "2026-10-31", 80), hint("2026-10-27", "2026-10-31", 85)]
    pairs = choose_date_pairs(params(), hints, 2)
    assert len(pairs) == 2 and pairs[0] != pairs[1]


# --- validation ------------------------------------------------------------

@pytest.mark.parametrize("kw", [
    {"depart_from": date(2026, 9, 1)},
    {"depart_to": date(2026, 10, 1)},
    {"depart_to": date(2026, 12, 31)},
    {"stay_min": 6, "stay_max": 5},
    {"origins": ()},
    {"live_calls": 5},
])
def test_invalid_params_rejected(kw):
    with pytest.raises(ValueError):
        params(**kw).validate(TODAY)


# --- orchestration ---------------------------------------------------------

def test_run_search_uses_two_live_calls_across_all_origins(tmp_path):
    calls = []

    def fake_live(key, quota, origins, dests, out, ret, adults, max_stops):
        quota.consume()
        calls.append((origins, dests, out, ret))
        return FIXTURE

    quota = SerpApiQuota(tmp_path / "q.json", limit=100)
    res = run_search(params(), serp_key="k", tp_token="", quota=quota, fetch_live=fake_live, today=TODAY)
    assert len(calls) == 2
    assert calls[0][0] == "TLS,BCN"
    assert quota.remaining() == 98
    assert len(res["offers"]) == 9  # mêmes offres dans les deux réponses : dédupliquées
    assert res["ranking"]["within_budget"] is False
    assert res["offers"][0]["bags"]["checked"] is True
    assert "offers_objects" in res


def test_run_search_respects_empty_quota(tmp_path):
    quota = SerpApiQuota(tmp_path / "q.json", limit=0)
    res = run_search(params(), serp_key="k", tp_token="", quota=quota,
                     fetch_live=lambda *a: pytest.fail("ne doit pas appeler"), today=TODAY)
    assert res["offers"] == []
    assert any("épuisé" in w for w in res["warnings"])


def test_run_search_survives_live_error(tmp_path):
    def boom(*a):
        raise requests.ConnectionError("réseau coupé")

    quota = SerpApiQuota(tmp_path / "q.json", limit=100)
    res = run_search(params(), serp_key="k", tp_token="", quota=quota, fetch_live=boom, today=TODAY)
    assert res["offers"] == []
    assert len(res["warnings"]) >= 2


def test_cache_failure_is_reported(tmp_path):
    def cache_boom(*a):
        raise requests.Timeout()

    quota = SerpApiQuota(tmp_path / "q.json", limit=0)
    res = run_search(params(), serp_key="k", tp_token="t", quota=quota, fetch_cache=cache_boom, today=TODAY)
    assert any("Cache" in w for w in res["warnings"])


# --- cache Travelpayouts ---------------------------------------------------

def test_parse_hints_filters_window_and_stay():
    rows = [
        {"origin_airport": "TLS", "destination_airport": "NAP", "departure_at": "2026-10-22T10:00:00+02:00",
         "return_at": "2026-10-26T10:00:00Z", "price": 99, "airline": "FR", "transfers": 0,
         "return_transfers": 0, "link": "/search/x"},
        {"origin_airport": "TLS", "destination_airport": "NAP", "departure_at": "2026-10-22T10:00:00+02:00",
         "return_at": "2026-11-05T10:00:00Z", "price": 50},
        {"departure_at": "garbage"},
    ]
    hints = parse_hints(rows, date(2026, 10, 20), date(2026, 10, 31), 4, 5)
    assert len(hints) == 1
    assert hints[0].price_eur == 99
    assert hints[0].link == "https://www.aviasales.com/search/x"


# --- bagages ---------------------------------------------------------------

def test_bag_info_and_warnings():
    assert bag_info(("1 checked bag up to 23 kg included",)) == {"carry_on": None, "checked": True}
    info = bag_info(("Carry-on bag not included", "Checked baggage for a fee"))
    assert info == {"carry_on": False, "checked": False}
    assert "cabine" in bag_warning(info, "cabin")
    assert "soute" in bag_warning(info, "checked")
    assert bag_warning({"carry_on": None, "checked": None}, "cabin") is None
    assert bag_warning(info, "none") is None


def test_low_cost_cabin_warning_only_when_unknown():
    unknown = {"carry_on": None, "checked": None}
    assert "Low-cost" in bag_warning(unknown, "cabin", ("easyJet",))
    assert bag_warning(unknown, "cabin", ("Air France",)) is None
    assert bag_warning({"carry_on": True, "checked": None}, "cabin", ("Ryanair",)) is None


def test_on_raw_receives_each_live_response(tmp_path):
    seen = []
    quota = SerpApiQuota(tmp_path / "q.json", limit=100)

    def fake_live(key, q, *a):
        q.consume()
        return FIXTURE

    run_search(params(), serp_key="k", tp_token="", quota=quota, fetch_live=fake_live, today=TODAY,
               on_raw=seen.append)
    assert len(seen) == 2

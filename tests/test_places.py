import pytest
import requests

from agent_vols import places
from agent_vols.places import search_places

LONDON = [
    {"type": "city", "code": "LON", "name": "Londres", "country_name": "Royaume-Uni"},
    {"type": "airport", "code": "STN", "name": "Stansted", "city_name": "Londres", "city_code": "LON", "country_name": "Royaume-Uni"},
    {"type": "airport", "code": "LHR", "name": "Heathrow", "city_name": "Londres", "city_code": "LON", "country_name": "Royaume-Uni"},
    {"type": "city", "code": "bad!", "name": "Invalide"},
]


@pytest.fixture(autouse=True)
def clear_cache():
    places._CACHE.clear()


def test_city_groups_its_airports():
    results, online = search_places("londres", fetch=lambda t: LONDON)
    assert online is True
    city = results[0]
    assert city["kind"] == "city" and city["label"] == "Londres"
    assert city["iata"] == ["STN", "LHR"]
    assert results[1]["label"] == "Londres · Stansted" and results[1]["iata"] == ["STN"]
    assert all(r["code"] != "BAD!" for r in results)


def test_single_airport_city_uses_own_code():
    rows = [{"type": "city", "code": "CUN", "name": "Cancún", "country_name": "Mexique"}]
    results, _ = search_places("cancun", fetch=lambda t: rows)
    assert results[0]["iata"] == ["CUN"] and results[0]["country"] == "Mexique"


def test_results_are_cached():
    calls = []
    search_places("londres", fetch=lambda t: calls.append(t) or LONDON)
    search_places("Londres ", fetch=lambda t: calls.append(t) or LONDON)
    assert len(calls) == 1


def test_offline_falls_back_to_local_list():
    def boom(t):
        raise requests.ConnectionError()

    results, online = search_places("veni", fetch=boom)
    assert online is False
    assert results[0]["iata"] == ["VCE", "TSF"]


def test_short_term_returns_nothing():
    assert search_places("a", fetch=lambda t: pytest.fail("pas d'appel")) == ([], True)

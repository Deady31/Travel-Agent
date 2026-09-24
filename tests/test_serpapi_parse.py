import json
from pathlib import Path

from agent_vols.serpapi_provider import parse_serpapi

FIXTURE = Path(__file__).parent / "fixtures" / "serpapi_tls_nap.json"


def load():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_parse_returns_all_offers():
    offers = parse_serpapi(load())
    assert len(offers) == 9


def test_every_offer_has_traceability_fields():
    for offer in parse_serpapi(load()):
        assert offer.source == "Google Flights via SerpApi"
        assert offer.fetched_at == "2026-09-24 07:38:08 UTC"
        assert offer.search_url.startswith("https://www.google.com/travel/flights")
        assert offer.id


def test_first_offer_values_match_raw_json():
    raw = load()
    first_raw = raw["best_flights"][0]
    offer = parse_serpapi(raw)[0]
    assert offer.price_eur == first_raw["price"] == 554
    assert offer.stops == 1
    assert offer.duration_min == 255
    assert offer.departure_time == "2026-10-28 13:30"
    assert offer.arrival_time == "2026-10-28 17:45"
    assert offer.airlines == ("Lufthansa", "Lufthansa City Airlines")
    assert offer.flight_numbers == ("LH 2219", "VL 1878")
    assert offer.origin == "TLS" and offer.destination == "NAP"
    assert offer.outbound_date == "2026-10-28" and offer.return_date == "2026-11-01"


def test_ids_are_unique_and_stable():
    ids_a = [o.id for o in parse_serpapi(load())]
    ids_b = [o.id for o in parse_serpapi(load())]
    assert ids_a == ids_b
    assert len(set(ids_a)) == len(ids_a)


def test_offers_without_price_are_skipped():
    raw = load()
    raw["best_flights"][0].pop("price")
    assert len(parse_serpapi(raw)) == 8


def test_offers_without_duration_are_skipped():
    raw = load()
    raw["other_flights"][0].pop("total_duration")
    assert len(parse_serpapi(raw)) == 8


def test_empty_response_returns_empty_list():
    raw = {"search_metadata": {"processed_at": "x", "google_flights_url": "https://www.google.com/travel/flights"},
           "search_parameters": {}}
    assert parse_serpapi(raw) == []

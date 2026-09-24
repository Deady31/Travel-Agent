from dataclasses import replace

import pytest

from agent_vols.models import Offer
from agent_vols.scoring import rank_offers, schedule_score


def make(id_, price, duration, stops, dep="2026-10-28 10:00", arr="2026-10-28 14:00"):
    return Offer(
        id=id_, source="test", fetched_at="now", origin="TLS", destination="NAP",
        outbound_date="2026-10-28", return_date="2026-11-01", price_eur=price,
        airlines=("X",), flight_numbers=("X1",), stops=stops, duration_min=duration,
        departure_time=dep, arrival_time=arr, search_url="https://example.com", fare_notes=(),
    )


def test_top3_categories_are_distinct():
    offers = [make("a", 100, 600, 2), make("b", 150, 200, 0), make("c", 120, 300, 1), make("d", 300, 150, 0)]
    result = rank_offers(offers, budget_eur=None)
    ids = [result["cheapest"]["id"], result["best_balance"]["id"], result["most_comfortable"]["id"]]
    assert result["cheapest"]["id"] == "a"
    assert len(set(ids)) == 3


def test_budget_filter_with_10_percent_tolerance():
    offers = [make("a", 160, 300, 1), make("b", 170, 300, 1)]
    result = rank_offers(offers, budget_eur=150)
    assert result["within_budget"] is True
    assert result["cheapest"]["id"] == "a"
    assert result["counts"]["kept"] == 1


def test_nothing_in_budget_is_flagged_not_hidden():
    offers = [make("a", 500, 300, 1), make("b", 600, 300, 1)]
    result = rank_offers(offers, budget_eur=100)
    assert result["within_budget"] is False
    assert result["cheapest"]["price_eur"] == 500


def test_fewer_than_three_offers():
    result = rank_offers([make("a", 100, 300, 1)], budget_eur=None)
    assert result["cheapest"]["id"] == "a"
    assert result["best_balance"] is None
    assert result["most_comfortable"] is None


def test_no_offers():
    result = rank_offers([], budget_eur=None)
    assert result["cheapest"] is None
    assert result["counts"]["total"] == 0


def test_prices_are_never_modified():
    offers = [make("a", 123.45, 300, 1), make("b", 99.99, 200, 0)]
    result = rank_offers(offers, budget_eur=None)
    assert {result["cheapest"]["price_eur"], result["best_balance"]["price_eur"]} == {123.45, 99.99}


def test_custom_weights_price_only_picks_cheapest_as_balance():
    offers = [make("a", 100, 900, 2), make("b", 110, 100, 0), make("c", 400, 100, 0)]
    result = rank_offers(offers, budget_eur=None,
                         weights={"price": 1, "duration": 0, "stops": 0, "schedule": 0})
    assert result["cheapest"]["id"] == "a"
    assert result["best_balance"]["id"] == "b"


def test_invalid_weights_rejected():
    with pytest.raises(ValueError):
        rank_offers([make("a", 1, 1, 0)], budget_eur=None, weights={"price": -1})
    with pytest.raises(ValueError):
        rank_offers([make("a", 1, 1, 0)], budget_eur=None, weights={"price": 0, "duration": 0, "stops": 0, "schedule": 0})


@pytest.mark.parametrize("dep,arr,expected", [
    ("2026-10-28 10:00", "2026-10-28 14:00", 1.0),
    ("2026-10-28 05:30", "2026-10-28 09:00", 0.5),
    ("2026-10-28 20:00", "2026-10-28 23:45", 0.5),
    ("2026-10-28 05:00", "2026-10-28 23:50", 0.0),
])
def test_schedule_score(dep, arr, expected):
    assert schedule_score(make("a", 1, 1, 0, dep, arr)) == expected


def test_access_time_penalizes_far_airports():
    near = replace(make("near", 100, 200, 0), origin="TLS")
    far = replace(make("far", 100, 150, 0), origin="BCN")
    without = rank_offers([near, far], budget_eur=None, weights={"price": 0, "duration": 1, "stops": 0, "schedule": 0})
    assert without["cheapest"]["id"] in {"near", "far"}
    with_access = rank_offers([near, far], budget_eur=None,
                              weights={"price": 0, "duration": 1, "stops": 0, "schedule": 0},
                              access_minutes={"TLS": 0, "BCN": 240})
    scores = {with_access["cheapest"]["id"]: with_access["cheapest"]["score"],
              with_access["best_balance"]["id"]: with_access["best_balance"]["score"]}
    assert scores["near"] > scores["far"]


def test_input_offers_not_mutated():
    offers = [make("a", 100, 300, 1)]
    snapshot = [replace(o) for o in offers]
    rank_offers(offers, budget_eur=50)
    assert offers == snapshot

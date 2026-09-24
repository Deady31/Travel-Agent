from datetime import date

import pytest

from agent_vols.parser import parse_command

TODAY = date(2026, 9, 24)


def p(text):
    return parse_command(text, today=TODAY)


def test_reference_request():
    r = p("Naples fin octobre, 4-5 jours, max 150 € A/R, bagage cabine")
    assert r.destination_iata == ("NAP",)
    assert (r.depart_from, r.depart_to) == ("2026-10-20", "2026-10-31")
    assert (r.stay_min, r.stay_max) == (4, 5)
    assert r.budget_eur == 150
    assert r.bag == "cabin"
    assert r.missing == ()


def test_short_syntax():
    r = p("naples fin oct 4-5j 150€ cabine")
    assert r.destination_iata == ("NAP",)
    assert (r.stay_min, r.stay_max) == (4, 5)
    assert r.budget_eur == 150


def test_exact_range_with_month():
    r = p("Lisbonne du 12 au 16 novembre")
    assert r.destination_iata == ("LIS",)
    assert (r.depart_from, r.depart_to) == ("2026-11-12", "2026-11-12")
    assert (r.stay_min, r.stay_max) == (4, 4)


def test_exact_range_numeric_across_months():
    r = p("rome du 28/10 au 02/11")
    assert r.depart_from == "2026-10-28"
    assert r.stay_min == 5
    assert r.destination_iata == ("FCO", "CIA")


def test_single_date_flexible():
    r = p("Porto le 14/11 flexible 3 jours direct")
    assert (r.depart_from, r.depart_to) == ("2026-11-11", "2026-11-17")
    assert r.max_stops == 0
    assert r.stay_min == 3


def test_week_and_multi_airport_region():
    r = p("Toscane début décembre, 1 semaine")
    assert r.destination_iata == ("PSA", "FLR")
    assert (r.depart_from, r.depart_to) == ("2026-12-01", "2026-12-10")
    assert (r.stay_min, r.stay_max) == (7, 7)


def test_past_month_rolls_to_next_year():
    r = p("Athènes en mars une semaine")
    assert r.depart_from == "2027-03-01"
    assert r.destination_iata == ("ATH",)


def test_passengers_and_checked_bag():
    r = p("Marrakech en décembre 5 jours 2 adultes valise en soute")
    assert r.adults == 2
    assert r.bag == "checked"


def test_missing_fields_reported():
    r = p("Je veux aller à Lisbonne")
    assert "period" in r.missing and "stay" in r.missing
    assert "destination" not in r.missing


def test_unknown_destination():
    r = p("Atlantide en novembre 3 jours")
    assert "destination" in r.missing
    assert r.destination_query == "atlantide"


def test_unknown_city_becomes_query():
    r = p("Je veux aller à Cancún en février, 10 jours, max 900€ avec valise en soute")
    assert r.destination_query == "cancun"
    assert r.stay_min == 10 and r.budget_eur == 900 and r.bag == "checked"


def test_known_city_has_no_query():
    assert p("naples fin oct 4-5j").destination_query is None


def test_ambiguous_destination():
    r = p("Santiago en avril 5 jours")
    assert "destination_choice" in r.missing
    assert len(r.destination_choices) == 2


def test_weekend():
    r = p("Berlin un week-end en novembre")
    assert (r.stay_min, r.stay_max) == (2, 3)


@pytest.mark.parametrize("text", ["", "   ", "???"])
def test_garbage_does_not_crash(text):
    r = p(text)
    assert "destination" in r.missing

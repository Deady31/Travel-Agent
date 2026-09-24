"""Lecture des mentions bagages fournies par Google Flights. Aucun montant n'est inventé."""

import re

CARRY_ON_EXCLUDED = re.compile(r"carry-?on bag not included|bagage (a main|cabine) non inclus", re.I)
CARRY_ON_INCLUDED = re.compile(r"carry-?on bag included|bagage (a main|cabine) inclus", re.I)
CHECKED_INCLUDED = re.compile(r"checked bag[^,]*included|bagage en soute[^,]*inclus", re.I)
CHECKED_FEE = re.compile(r"checked bag(gage)?[^,]*(fee|not included)|bagage en soute[^,]*(payant|non inclus)", re.I)


def bag_info(fare_notes: tuple[str, ...]) -> dict:
    """True = inclus, False = payant / non inclus, None = pas d'information."""
    text = " | ".join(fare_notes)
    carry_on = False if CARRY_ON_EXCLUDED.search(text) else (True if CARRY_ON_INCLUDED.search(text) else None)
    checked = True if CHECKED_INCLUDED.search(text) else (False if CHECKED_FEE.search(text) else None)
    return {"carry_on": carry_on, "checked": checked}


# Compagnies dont le tarif de base ne comprend qu'un petit sac sous le siège (valise cabine 10 kg payante).
LOW_COST = {"easyjet", "ryanair", "wizz air", "vueling", "volotea", "transavia", "transavia france"}


def bag_warning(info: dict, bag: str, airlines: tuple[str, ...] = ()) -> str | None:
    """Message à afficher quand le bagage voulu risque d'être en supplément."""
    if bag == "checked" and info["checked"] is not True:
        return "Bagage soute probablement en supplément : à vérifier chez la compagnie."
    if bag == "cabin" and info["carry_on"] is False:
        return "Bagage cabine non inclus : supplément à prévoir."
    if bag == "cabin" and info["carry_on"] is None and any(a.lower() in LOW_COST for a in airlines):
        return "Low-cost : valise cabine en général payante sur le tarif de base, à vérifier."
    return None

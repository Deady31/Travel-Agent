"""Lecture déterministe d'une commande en français : « naples fin oct 4-5j 150€ cabine »."""

import calendar
import re
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta

from agent_vols.airports import find_destination_in, normalize

MONTHS = {
    "janvier": 1, "janv": 1, "jan": 1, "fevrier": 2, "fevr": 2, "fev": 2, "mars": 3, "avril": 4, "avr": 4,
    "mai": 5, "juin": 6, "juillet": 7, "juil": 7, "aout": 8, "septembre": 9, "sept": 9, "sep": 9,
    "octobre": 10, "oct": 10, "novembre": 11, "nov": 11, "decembre": 12, "dec": 12,
}
MONTH_RE = "|".join(sorted(MONTHS, key=len, reverse=True))
# Mots à ignorer pour isoler une destination inconnue : « je veux aller à Cancun en cabine » -> « cancun »
STOPWORDS = set("""
je j veux voudrais aimerais aller partir partirais voyager a au aux en pour vers de d du des le la les l un une
bagage bagages cabine soute valise sac main petit juste sans direct escale escales max maximum ar r aller retour
adulte adultes personne personnes pers voyageur voyageurs vol vols billet billets flexible week end et avec
jours jour j nuits nuit semaine semaines deux trois euros euro eur mois debut mi fin moins cher pas s il te plait
""".split())
DAY_UNIT = r"(?:j|jours?|nuits?)\b"
FLEX_DAYS = 3


@dataclass(frozen=True)
class TripRequest:
    destination_text: str | None = None
    destination_iata: tuple[str, ...] = ()
    destination_label: str | None = None
    destination_choices: tuple[dict, ...] = ()
    destination_query: str | None = None
    depart_from: str | None = None
    depart_to: str | None = None
    stay_min: int | None = None
    stay_max: int | None = None
    budget_eur: float | None = None
    adults: int = 1
    bag: str = "cabin"
    max_stops: int = 1
    missing: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return asdict(self)


def _year_for(month: int, day: int, today: date) -> int:
    candidate = date(today.year, month, min(day, calendar.monthrange(today.year, month)[1]))
    return today.year if candidate >= today else today.year + 1


def _mkdate(day: int, month: int, today: date) -> date:
    year = _year_for(month, day, today)
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def _parse_period(text: str, today: date) -> tuple[date | None, date | None, date | None, str]:
    """Renvoie (début fenêtre, fin fenêtre, date retour exacte éventuelle, texte restant)."""
    # « du 12 au 16 novembre » / « du 28/10 au 02/11 »
    m = re.search(rf"du (\d{{1,2}})(?:/(\d{{1,2}})| ({MONTH_RE}))? au (\d{{1,2}})(?:/(\d{{1,2}})| ({MONTH_RE}))", text)
    if m:
        end_month = int(m.group(5)) if m.group(5) else MONTHS[m.group(6)]
        start_month = int(m.group(2)) if m.group(2) else (MONTHS[m.group(3)] if m.group(3) else end_month)
        start = _mkdate(int(m.group(1)), start_month, today)
        end = _mkdate(int(m.group(4)), end_month, today)
        if end <= start:
            end = end.replace(year=end.year + 1)
        return start, start, end, text.replace(m.group(0), " ")

    flexible = bool(re.search(r"flexible|±\s*3|\+/-\s*3", text))

    # « le 14/11 »
    m = re.search(r"\b(\d{1,2})/(\d{1,2})\b", text)
    if m:
        d = _mkdate(int(m.group(1)), int(m.group(2)), today)
        return _window(d, flexible, today) + (None, text.replace(m.group(0), " "))

    # « 14 novembre »
    m = re.search(rf"\b(\d{{1,2}}) ({MONTH_RE})\b", text)
    if m:
        d = _mkdate(int(m.group(1)), MONTHS[m.group(2)], today)
        return _window(d, flexible, today) + (None, text.replace(m.group(0), " "))

    # « début / mi / fin novembre », « en novembre »
    m = re.search(rf"\b(?:(debut|mi|fin) )?(?:de |d )?({MONTH_RE})\b", text)
    if m:
        month = MONTHS[m.group(2)]
        year = _year_for(month, calendar.monthrange(today.year, month)[1], today)
        last = calendar.monthrange(year, month)[1]
        lo, hi = {"debut": (1, 10), "mi": (10, 20), "fin": (20, last)}.get(m.group(1), (1, last))
        start, end = date(year, month, lo), date(year, month, hi)
        return max(start, today), end, None, text.replace(m.group(0), " ")

    return None, None, None, text


def _window(d: date, flexible: bool, today: date) -> tuple[date, date]:
    if not flexible:
        return d, d
    return max(d - timedelta(days=FLEX_DAYS), today), d + timedelta(days=FLEX_DAYS)


def _parse_stay(text: str) -> tuple[int | None, int | None, str]:
    patterns = [
        (rf"(\d+)\s*(?:-|a\b|\s)\s*(\d+)\s*{DAY_UNIT}", lambda m: (int(m.group(1)), int(m.group(2)))),
        (rf"(\d+)\s*{DAY_UNIT}", lambda m: (int(m.group(1)), int(m.group(1)))),
        (r"\b(?:une|1) semaine\b", lambda m: (7, 7)),
        (r"\b(?:deux|2) semaines\b", lambda m: (14, 14)),
        (r"\bweek ?end\b", lambda m: (2, 3)),
    ]
    for pattern, extract in patterns:
        m = re.search(pattern, text)
        if m:
            lo, hi = sorted(extract(m))
            return lo, hi, text.replace(m.group(0), " ")
    return None, None, text


def parse_command(command: str, today: date | None = None) -> TripRequest:
    today = today or date.today()
    text = f" {normalize(command.replace('€', ' euros '))} "

    budget = None
    m = re.search(r"(?:max(?:imum)? )?(\d{2,5})\s*(?:euros?|eur)\b", text) or re.search(r"\bmax(?:imum)? (\d{2,5})\b", text)
    if m:
        budget = float(m.group(1))
        text = text.replace(m.group(0), " ")

    adults = 1
    m = re.search(r"(\d)\s*(?:adultes?|personnes?|pers\b|voyageurs?)", text)
    if m:
        adults = int(m.group(1))
        text = text.replace(m.group(0), " ")
    elif re.search(r"\ba deux\b", text):
        adults = 2

    bag = "cabin"
    if re.search(r"\b(soute|valise)\b", text):
        bag = "checked"
    elif re.search(r"sans bagage|juste un sac|petit sac", text):
        bag = "none"

    max_stops = 0 if re.search(r"\bdirect|sans escale", text) else 1

    depart_from, depart_to, return_date, text = _parse_period(text, today)
    stay_min, stay_max, text = _parse_stay(text)
    if return_date and depart_from:
        stay_min = stay_max = (return_date - depart_from).days

    found = find_destination_in(command) or find_destination_in(text)
    dest_text, resolved = found if found else (None, {})
    leftover = " ".join(w for w in re.findall(r"[a-z]+", text) if w not in STOPWORDS and len(w) > 1)
    query = None if found else (leftover or None)

    missing = []
    if not resolved.get("iata") and not resolved.get("choices"):
        missing.append("destination")
    if resolved.get("choices"):
        missing.append("destination_choice")
    if depart_from is None:
        missing.append("period")
    if stay_min is None:
        missing.append("stay")

    return TripRequest(
        destination_text=dest_text,
        destination_iata=tuple(resolved.get("iata", ())),
        destination_label=resolved.get("label"),
        destination_choices=tuple(resolved.get("choices", ())),
        destination_query=query,
        depart_from=depart_from.isoformat() if depart_from else None,
        depart_to=depart_to.isoformat() if depart_to else None,
        stay_min=stay_min,
        stay_max=stay_max,
        budget_eur=budget,
        adults=adults,
        bag=bag,
        max_stops=max_stops,
        missing=tuple(missing),
    )

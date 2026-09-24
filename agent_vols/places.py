"""Recherche de destinations dans le monde entier (villes et aéroports, noms en français).

Source : autocomplétion publique Travelpayouts (gratuite, sans clé, sans quota SerpApi).
Repli hors ligne : la liste locale de agent_vols/data/airports.json.
"""

from collections import OrderedDict

import requests

from agent_vols import airports

ENDPOINT = "https://autocomplete.travelpayouts.com/places2"
MAX_RESULTS = 8
_CACHE: OrderedDict[str, list[dict]] = OrderedDict()
_CACHE_SIZE = 256


def _fetch(term: str) -> list[dict]:
    params = {"term": term, "locale": "fr", "types[]": ["city", "airport"]}
    resp = requests.get(ENDPOINT, params=params, timeout=8)
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, list) else []


def _from_api(rows: list[dict]) -> list[dict]:
    """Regroupe : une ville propose tous ses aéroports présents dans la réponse."""
    airports_by_city: dict[str, list[str]] = {}
    for row in rows:
        if row.get("type") == "airport" and row.get("city_code") and row.get("code"):
            airports_by_city.setdefault(row["city_code"], []).append(row["code"])

    places = []
    for row in rows:
        code = str(row.get("code", "")).upper()
        if len(code) != 3 or not code.isalpha():
            continue
        if row.get("type") == "city":
            iata = airports_by_city.get(code) or [code]
            places.append({"kind": "city", "label": row.get("name", code), "country": row.get("country_name", ""),
                           "iata": iata, "code": code})
        elif row.get("type") == "airport":
            city = row.get("city_name") or ""
            label = f"{city} · {row.get('name', code)}" if city else row.get("name", code)
            places.append({"kind": "airport", "label": label, "country": row.get("country_name", ""),
                           "iata": [code], "code": code})
    # Les villes (qui regroupent leurs aéroports) d'abord, l'ordre de pertinence de l'API est conservé.
    return sorted(places, key=lambda p: p["kind"] != "city")[:MAX_RESULTS]


def _from_local(term: str) -> list[dict]:
    key = airports.normalize(term)
    names = airports.destination_names()
    hits = [n for n in names if n.startswith(key)] + [n for n in names if key in n and not n.startswith(key)]
    places = []
    for name in hits[:MAX_RESULTS]:
        resolved = airports.resolve_destination(name)
        if resolved.get("iata"):
            places.append({"kind": "city", "label": name.title(), "country": "", "iata": resolved["iata"],
                           "code": resolved["iata"][0]})
    return places


def search_places(term: str, fetch=_fetch) -> tuple[list[dict], bool]:
    """Renvoie (résultats, en_ligne). en_ligne=False si le repli local a été utilisé."""
    term = term.strip()[:60]
    if len(term) < 2:
        return [], True
    key = airports.normalize(term)
    if key in _CACHE:
        _CACHE.move_to_end(key)
        return _CACHE[key], True
    try:
        places = _from_api(fetch(term))
    except (requests.RequestException, ValueError):
        return _from_local(term), False
    _CACHE[key] = places
    if len(_CACHE) > _CACHE_SIZE:
        _CACHE.popitem(last=False)
    return places, True

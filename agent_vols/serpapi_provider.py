import hashlib

import requests

from agent_vols.models import Offer
from agent_vols.quota import SerpApiQuota

SOURCE = "Google Flights via SerpApi"
ENDPOINT = "https://serpapi.com/search.json"


def _offer_id(params: dict, flight_numbers: tuple[str, ...], price) -> str:
    raw = "|".join([SOURCE, params.get("outbound_date", ""), params.get("return_date", ""),
                    *flight_numbers, str(price)])
    return hashlib.sha1(raw.encode()).hexdigest()[:10]


def _to_offer(item: dict, params: dict, fetched_at: str, search_url: str) -> Offer | None:
    legs = item.get("flights") or []
    price = item.get("price")
    duration = item.get("total_duration")
    if not legs or price is None or duration is None:
        return None
    flight_numbers = tuple(leg.get("flight_number", "") for leg in legs)
    return Offer(
        id=_offer_id(params, flight_numbers, price),
        source=SOURCE,
        fetched_at=fetched_at,
        origin=legs[0]["departure_airport"]["id"],
        destination=legs[-1]["arrival_airport"]["id"],
        outbound_date=params.get("outbound_date", ""),
        return_date=params.get("return_date", ""),
        price_eur=price,
        airlines=tuple(leg.get("airline", "") for leg in legs),
        flight_numbers=flight_numbers,
        stops=len(legs) - 1,
        duration_min=duration,
        departure_time=legs[0]["departure_airport"]["time"],
        arrival_time=legs[-1]["arrival_airport"]["time"],
        search_url=search_url,
        fare_notes=tuple(item.get("extensions", [])),
    )


def parse_serpapi(raw: dict) -> list[Offer]:
    """Convertit une réponse Google Flights (SerpApi) en offres, sans jamais toucher aux prix."""
    meta = raw.get("search_metadata", {})
    params = raw.get("search_parameters", {})
    fetched_at = meta.get("processed_at") or meta.get("created_at", "")
    search_url = meta.get("google_flights_url", "")
    items = raw.get("best_flights", []) + raw.get("other_flights", [])
    offers = (_to_offer(item, params, fetched_at, search_url) for item in items)
    return [o for o in offers if o is not None]


def fetch_serpapi(api_key: str, quota: SerpApiQuota, origin: str, destination: str,
                  outbound_date: str, return_date: str, adults: int = 1, max_stops: int = 1) -> dict:
    """Appel live. Consomme 1 unité de quota avant l'appel."""
    quota.consume()
    params = {
        "engine": "google_flights",
        "departure_id": origin,
        "arrival_id": destination,
        "outbound_date": outbound_date,
        "return_date": return_date,
        "type": "1",
        "adults": adults,
        # SerpApi : 0 = tous, 1 = direct, 2 = 1 escale max, 3 = 2 escales max
        "stops": max_stops + 1,
        "currency": "EUR",
        "hl": "fr",
        "gl": "fr",
        "api_key": api_key,
    }
    resp = requests.get(ENDPOINT, params=params, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"SerpApi : {data['error']}")
    return data

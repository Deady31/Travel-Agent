"""Prix en cache Aviasales (Travelpayouts). Sert à repérer les bonnes dates, jamais à affirmer un prix."""

from dataclasses import asdict, dataclass
from datetime import date

import requests

SOURCE = "Aviasales (cache)"
ENDPOINT = "https://api.travelpayouts.com/aviasales/v3/prices_for_dates"


@dataclass(frozen=True)
class CacheHint:
    origin: str
    destination: str
    outbound_date: str
    return_date: str
    price_eur: float
    airline: str
    stops: int
    link: str
    source: str = SOURCE

    def to_dict(self) -> dict:
        return asdict(self)


def fetch_month(token: str, origin: str, destination: str, month: str) -> list[dict]:
    params = {"origin": origin, "destination": destination, "departure_at": month,
              "currency": "eur", "sorting": "price", "one_way": "false", "limit": 100}
    resp = requests.get(ENDPOINT, params=params, headers={"X-Access-Token": token}, timeout=30)
    resp.raise_for_status()
    return resp.json().get("data", [])


def parse_hints(rows: list[dict], depart_from: date, depart_to: date,
                stay_min: int, stay_max: int) -> list[CacheHint]:
    hints = []
    for row in rows:
        try:
            out = date.fromisoformat(row["departure_at"][:10])
            ret = date.fromisoformat(row["return_at"][:10])
            price = float(row["price"])
        except (KeyError, TypeError, ValueError):
            continue
        if not (depart_from <= out <= depart_to and stay_min <= (ret - out).days <= stay_max):
            continue
        hints.append(CacheHint(
            origin=row.get("origin_airport") or row.get("origin", ""),
            destination=row.get("destination_airport") or row.get("destination", ""),
            outbound_date=out.isoformat(),
            return_date=ret.isoformat(),
            price_eur=price,
            airline=row.get("airline", ""),
            stops=int(row.get("transfers", 0)) + int(row.get("return_transfers", 0)),
            link="https://www.aviasales.com" + row["link"] if row.get("link", "").startswith("/") else "",
        ))
    return sorted(hints, key=lambda h: h.price_eur)

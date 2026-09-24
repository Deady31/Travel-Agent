"""Orchestration V1 : cache gratuit pour choisir les dates, puis 1-2 appels live multi-aéroports."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, timedelta

import requests

from agent_vols import airports
from agent_vols.bags import bag_info, bag_warning
from agent_vols.models import Offer
from agent_vols.quota import QuotaExceeded, SerpApiQuota
from agent_vols.scoring import door_to_door, rank_offers
from agent_vols.serpapi_provider import fetch_serpapi, parse_serpapi
from agent_vols.travelpayouts_provider import fetch_month, parse_hints

MAX_LIVE_CALLS = 2
MAX_WINDOW_DAYS = 45
PREFERRED_WEEKDAYS = {1, 2}  # mardi, mercredi : souvent moins chers


@dataclass(frozen=True)
class SearchParams:
    destination_iata: tuple[str, ...]
    origins: tuple[str, ...]
    depart_from: date
    depart_to: date
    stay_min: int
    stay_max: int
    budget_eur: float | None = None
    adults: int = 1
    bag: str = "cabin"
    max_stops: int = 1
    live_calls: int = MAX_LIVE_CALLS

    def validate(self, today: date) -> None:
        if not self.destination_iata or not self.origins:
            raise ValueError("Destination et au moins un aéroport de départ requis.")
        if self.depart_from < today:
            raise ValueError("La période de départ est dans le passé.")
        if self.depart_to < self.depart_from:
            raise ValueError("Fin de période avant le début.")
        if (self.depart_to - self.depart_from).days > MAX_WINDOW_DAYS:
            raise ValueError(f"Période trop large (max {MAX_WINDOW_DAYS} jours).")
        if not 1 <= self.stay_min <= self.stay_max <= 60:
            raise ValueError("Durée de séjour invalide.")
        if not 1 <= self.live_calls <= MAX_LIVE_CALLS:
            raise ValueError(f"live_calls doit être entre 1 et {MAX_LIVE_CALLS}.")


def _all_pairs(p: SearchParams) -> list[tuple[date, date]]:
    days = (p.depart_to - p.depart_from).days
    return [(p.depart_from + timedelta(d), p.depart_from + timedelta(d + s))
            for d in range(days + 1) for s in range(p.stay_min, p.stay_max + 1)]


def choose_date_pairs(p: SearchParams, hints: list, n: int) -> list[tuple[date, date]]:
    """Les n couples de dates à vérifier en live : d'abord les moins chers du cache, puis heuristique."""
    chosen: list[tuple[date, date]] = []
    for h in hints:
        pair = (date.fromisoformat(h.outbound_date), date.fromisoformat(h.return_date))
        if pair not in chosen:
            chosen.append(pair)
        if len(chosen) == n:
            return chosen
    mid = p.depart_from + (p.depart_to - p.depart_from) / 2
    fallback = sorted(
        _all_pairs(p),
        key=lambda pr: (pr[0].weekday() not in PREFERRED_WEEKDAYS, abs((pr[0] - mid).days), -(pr[1] - pr[0]).days),
    )
    for pair in fallback:
        if len(chosen) == n:
            break
        if all(pair[0] != c[0] for c in chosen):
            chosen.append(pair)
    return chosen


def _months(p: SearchParams) -> list[str]:
    months = {(p.depart_from + timedelta(d)).strftime("%Y-%m") for d in range((p.depart_to - p.depart_from).days + 1)}
    return sorted(months)


def collect_hints(p: SearchParams, token: str, fetch_cache=fetch_month) -> tuple[list, list[str]]:
    if not token:
        return [], ["Pas de token Travelpayouts : choix des dates par heuristique."]
    jobs = [(o, d, m) for o in p.origins for d in p.destination_iata for m in _months(p)]
    warnings: list[str] = []

    def run(job):
        try:
            return fetch_cache(token, *job)
        except requests.RequestException:
            return None

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(run, jobs))
    if any(r is None for r in results):
        warnings.append("Cache Aviasales partiellement indisponible.")
    rows = [row for r in results if r for row in r]
    return parse_hints(rows, p.depart_from, p.depart_to, p.stay_min, p.stay_max), warnings


def _enrich(offer: Offer, bag: str, access: dict[str, int]) -> dict:
    info = bag_info(offer.fare_notes)
    origin_meta = airports.origins().get(offer.origin, {})
    return {
        **offer.to_dict(),
        "origin_name": origin_meta.get("name", offer.origin),
        "access_min": access.get(offer.origin, 0),
        "door_to_door_min": door_to_door(offer, access),
        "bags": info,
        "bag_warning": bag_warning(info, bag, offer.airlines),
    }


def run_search(p: SearchParams, *, serp_key: str, tp_token: str, quota: SerpApiQuota,
               fetch_live=fetch_serpapi, fetch_cache=fetch_month, today: date | None = None,
               on_raw=None) -> dict:
    """on_raw(raw) : appelé avec chaque réponse live brute (journal de traçabilité)."""
    p.validate(today or date.today())
    access = airports.access_minutes()
    hints, warnings = collect_hints(p, tp_token, fetch_cache)

    n_calls = min(p.live_calls, quota.remaining())
    if n_calls == 0:
        warnings.append("Quota SerpApi épuisé ce mois-ci : seules les pistes du cache sont affichées (non vérifiées).")
    pairs = choose_date_pairs(p, hints, n_calls) if n_calls else []

    offers: list[Offer] = []
    searched, insights = [], []
    for out, ret in pairs:
        try:
            raw = fetch_live(serp_key, quota, ",".join(p.origins), ",".join(p.destination_iata),
                             out.isoformat(), ret.isoformat(), p.adults, p.max_stops)
        except QuotaExceeded:
            warnings.append("Quota SerpApi atteint pendant la recherche.")
            break
        except (requests.RequestException, RuntimeError) as exc:
            warnings.append(f"Recherche live {out} → {ret} impossible : {exc}")
            continue
        if on_raw:
            on_raw(raw)
        found = parse_serpapi(raw)
        offers.extend(found)
        searched.append({"outbound_date": out.isoformat(), "return_date": ret.isoformat(), "offers": len(found)})
        pi = raw.get("price_insights") or {}
        if pi:
            insights.append({"outbound_date": out.isoformat(), "return_date": ret.isoformat(),
                             "lowest_price": pi.get("lowest_price"), "price_level": pi.get("price_level"),
                             "typical_price_range": pi.get("typical_price_range")})

    unique = list({o.id: o for o in offers}.values())
    return {
        "offers_objects": unique,
        "offers": [_enrich(o, p.bag, access) for o in unique],
        "ranking": rank_offers(unique, p.budget_eur, None, access),
        "searched": searched,
        "price_insights": insights,
        "cache_hints": [h.to_dict() for h in hints[:10]],
        "warnings": warnings,
        "quota_remaining": quota.remaining(),
    }

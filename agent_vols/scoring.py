"""Scoring déterministe (PLAN.md §5). Bagages signalés à part, fiabilité compagnie pas encore intégrée."""

from agent_vols.models import Offer

DEFAULT_WEIGHTS = {"price": 0.50, "duration": 0.22, "stops": 0.17, "schedule": 0.11}
COMFORT_WEIGHTS = {"price": 0.17, "duration": 0.33, "stops": 0.28, "schedule": 0.22}
BUDGET_TOLERANCE = 1.10
COMFORT_BUDGET_CAP = 1.20
STOPS_SCORE = {0: 1.0, 1: 0.4}


def _validate_weights(weights: dict | None) -> dict:
    if weights is None:
        return DEFAULT_WEIGHTS
    unknown = set(weights) - set(DEFAULT_WEIGHTS)
    if unknown:
        raise ValueError(f"Poids inconnus : {sorted(unknown)}")
    merged = {**DEFAULT_WEIGHTS, **weights}
    if any(v < 0 for v in merged.values()):
        raise ValueError("Les poids doivent être positifs.")
    total = sum(merged.values())
    if total == 0:
        raise ValueError("Au moins un poids doit être non nul.")
    return {k: v / total for k, v in merged.items()}


def _normalize_low_is_better(value: float, lo: float, hi: float) -> float:
    return 1.0 if hi == lo else (hi - value) / (hi - lo)


def schedule_score(offer: Offer) -> float:
    dep_hour = offer.departure_time[-5:]
    arr_hour = offer.arrival_time[-5:]
    score = 1.0
    if dep_hour < "06:00":
        score -= 0.5
    if arr_hour > "23:30":
        score -= 0.5
    return score


def door_to_door(offer: Offer, access: dict[str, int]) -> int:
    """Durée du vol aller + trajet estimé jusqu'à l'aéroport de départ."""
    return offer.duration_min + access.get(offer.origin, 0)


def _score(offer: Offer, pool: list[Offer], weights: dict, access: dict[str, int]) -> float:
    prices = [o.price_eur for o in pool]
    durations = [door_to_door(o, access) for o in pool]
    parts = {
        "price": _normalize_low_is_better(offer.price_eur, min(prices), max(prices)),
        "duration": _normalize_low_is_better(door_to_door(offer, access), min(durations), max(durations)),
        "stops": STOPS_SCORE.get(offer.stops, 0.0),
        "schedule": schedule_score(offer),
    }
    return round(100 * sum(weights[k] * parts[k] for k in weights), 1)


def _entry(offer: Offer | None, score: float | None) -> dict | None:
    if offer is None:
        return None
    return {**offer.to_dict(), "score": score}


def rank_offers(offers: list[Offer], budget_eur: float | None, weights: dict | None = None,
                access_minutes: dict[str, int] | None = None) -> dict:
    balance_w = _validate_weights(weights)
    access = access_minutes or {}
    within = [o for o in offers if budget_eur is None or o.price_eur <= budget_eur * BUDGET_TOLERANCE]
    within_budget = bool(within) or budget_eur is None
    pool = within if within else list(offers)

    if not pool:
        return {"cheapest": None, "best_balance": None, "most_comfortable": None,
                "within_budget": within_budget, "counts": {"total": 0, "kept": 0}, "weights": balance_w}

    balance = {o.id: _score(o, pool, balance_w, access) for o in pool}
    comfort = {o.id: _score(o, pool, COMFORT_WEIGHTS, access) for o in pool}

    cheapest = min(pool, key=lambda o: (o.price_eur, -balance[o.id]))
    rest = [o for o in pool if o.id != cheapest.id]
    best = max(rest, key=lambda o: balance[o.id], default=None)
    rest = [o for o in rest if best is None or o.id != best.id]
    cap = None if budget_eur is None else budget_eur * COMFORT_BUDGET_CAP
    comfy_pool = [o for o in rest if cap is None or not within_budget or o.price_eur <= cap]
    comfy = max(comfy_pool, key=lambda o: comfort[o.id], default=None)

    return {
        "cheapest": _entry(cheapest, balance[cheapest.id]),
        "best_balance": _entry(best, balance[best.id] if best else None),
        "most_comfortable": _entry(comfy, comfort[comfy.id] if comfy else None),
        "within_budget": within_budget,
        "counts": {"total": len(offers), "kept": len(within)},
        "weights": balance_w,
    }

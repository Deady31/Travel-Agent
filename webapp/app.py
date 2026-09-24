"""App web locale « Départs » : barre de commande, filtres, cartes d'embarquement."""

import json
import logging
import os
import re
from datetime import date, datetime
from pathlib import Path
from typing import Annotated, Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, StringConstraints

from agent_vols import airports
from agent_vols.airports import normalize
from agent_vols.models import Offer
from agent_vols.parser import parse_command
from agent_vols.places import search_places
from agent_vols.quota import SerpApiQuota
from agent_vols.scoring import rank_offers
from agent_vols.search import MAX_LIVE_CALLS, SearchParams, run_search

ROOT = Path(__file__).resolve().parent.parent
STATIC = Path(__file__).parent / "static"
load_dotenv(ROOT / ".env")

SERPAPI_KEY = os.getenv("SERPAPI_KEY", "").strip()
TRAVELPAYOUTS_TOKEN = os.getenv("TRAVELPAYOUTS_TOKEN", "").strip()
DEMO_MODE = os.getenv("AGENT_VOLS_DEMO") == "1"
DEMO_FIXTURE = ROOT / "tests" / "fixtures" / "serpapi_tls_nap.json"
QUOTA = SerpApiQuota(ROOT / "data" / "serpapi_quota.json")
LOG_DIR = ROOT / "logs"
MAX_STORED_OFFERS = 2000

log = logging.getLogger("agent_vols")
app = FastAPI(title="Agent Vols", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=STATIC), name="static")

_offers: dict[str, Offer] = {}


@app.middleware("http")
async def revalidate_assets(request, call_next):
    """App locale : toujours revalider HTML/JS/CSS pour éviter une vieille version en cache après mise à jour."""
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache"
    return response

Iata = Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]


class ParseIn(BaseModel):
    text: str = Field(min_length=1, max_length=300)


class SearchIn(BaseModel):
    destination_iata: list[Iata] = Field(min_length=1, max_length=6)
    origins: list[Iata] = Field(min_length=1, max_length=6)
    depart_from: date
    depart_to: date
    stay_min: int = Field(ge=1, le=60)
    stay_max: int = Field(ge=1, le=60)
    budget_eur: float | None = Field(default=None, ge=0, le=20000)
    adults: int = Field(default=1, ge=1, le=9)
    bag: Literal["none", "cabin", "checked"] = "cabin"
    max_stops: int = Field(default=1, ge=0, le=2)
    live_calls: int = Field(default=MAX_LIVE_CALLS, ge=1, le=MAX_LIVE_CALLS)


class RankIn(BaseModel):
    offer_ids: list[str] = Field(max_length=500)
    budget_eur: float | None = Field(default=None, ge=0, le=20000)
    weights: dict[str, float] | None = None


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/config")
def config() -> dict:
    return {
        "origins": airports.origins(),
        "quota_remaining": QUOTA.remaining(),
        "quota_limit": QUOTA.limit,
        "has_live_key": bool(SERPAPI_KEY) or DEMO_MODE,
        "has_cache_token": bool(TRAVELPAYOUTS_TOKEN),
        "demo": DEMO_MODE,
        "today": date.today().isoformat(),
    }


@app.get("/api/places")
def places(q: str = Query(min_length=2, max_length=60)) -> dict:
    results, online = search_places(q)
    return {"results": results, "online": online}


@app.post("/api/parse")
def parse(body: ParseIn) -> dict:
    """Lit la commande ; une ville hors liste locale est cherchée dans le monde entier."""
    req = parse_command(body.text).to_dict()
    req["destination_suggestions"] = []
    if req["destination_query"] and not req["destination_iata"]:
        results, _ = search_places(req["destination_query"])
        query = normalize(req["destination_query"])
        best = results[0] if results else None
        # « bali » -> « Denpasar (Bali) » : le mot cherché doit apparaître en entier dans le nom.
        if best and re.search(rf"\b{re.escape(query)}\b", normalize(best["label"])):
            req["destination_iata"] = best["iata"]
            req["destination_label"] = best["label"]
            req["missing"] = [m for m in req["missing"] if m != "destination"]
        else:
            req["destination_suggestions"] = results[:5]
    return req


def _log_raw(raw: dict) -> None:
    """Journal des réponses brutes : chaque prix affiché reste traçable (logs/AAAA-MM-JJ.jsonl)."""
    LOG_DIR.mkdir(exist_ok=True)
    text = json.dumps({"logged_at": datetime.now().isoformat(timespec="seconds"), "raw": raw}, ensure_ascii=False)
    for secret in (SERPAPI_KEY, TRAVELPAYOUTS_TOKEN):
        if secret:
            text = text.replace(secret, "***")
    with open(LOG_DIR / f"{date.today().isoformat()}.jsonl", "a", encoding="utf-8") as fh:
        fh.write(text + "\n")


def _demo_search(params: SearchParams) -> dict:
    """Rejoue une réponse Google Flights enregistrée : aucun appel réseau, aucun quota."""
    raw = json.loads(DEMO_FIXTURE.read_text(encoding="utf-8"))
    result = run_search(params, serp_key="demo", tp_token="", quota=SerpApiQuota(ROOT / "data" / "demo_quota.json", 10**9),
                        fetch_live=lambda *a: raw, today=params.depart_from)
    result["warnings"] = [w for w in result["warnings"] if "Travelpayouts" not in w]
    result["warnings"].insert(0,"Mode démo : données Google Flights enregistrées le 24/09/2026 (TLS → NAP, 28/10 → 01/11), quelle que soit la demande.")
    result["quota_remaining"] = QUOTA.remaining()
    return result


@app.post("/api/search")
def search(body: SearchIn) -> dict:
    if not SERPAPI_KEY and not DEMO_MODE:
        raise HTTPException(400, "Clé SERPAPI_KEY absente du fichier .env.")
    unknown = set(body.origins) - set(airports.origins())
    if unknown:
        raise HTTPException(400, f"Aéroports de départ non gérés : {sorted(unknown)}")
    params = SearchParams(
        destination_iata=tuple(body.destination_iata), origins=tuple(body.origins),
        depart_from=body.depart_from, depart_to=body.depart_to,
        stay_min=body.stay_min, stay_max=body.stay_max, budget_eur=body.budget_eur,
        adults=body.adults, bag=body.bag, max_stops=body.max_stops, live_calls=body.live_calls,
    )
    try:
        if DEMO_MODE:
            result = _demo_search(params)
        else:
            result = run_search(params, serp_key=SERPAPI_KEY, tp_token=TRAVELPAYOUTS_TOKEN, quota=QUOTA,
                                on_raw=_log_raw)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        log.exception("Recherche échouée")
        raise HTTPException(500, "La recherche a échoué. Réessaie dans un instant.") from exc

    if len(_offers) > MAX_STORED_OFFERS:
        _offers.clear()
    _offers.update({o.id: o for o in result.pop("offers_objects")})
    return result


@app.post("/api/rank")
def rank(body: RankIn) -> dict:
    missing = [i for i in body.offer_ids if i not in _offers]
    if missing:
        raise HTTPException(404, "Offres expirées : relance la recherche.")
    try:
        return rank_offers([_offers[i] for i in body.offer_ids], body.budget_eur, body.weights,
                           airports.access_minutes())
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


def main() -> None:
    import threading
    import webbrowser

    import uvicorn

    port = int(os.getenv("AGENT_VOLS_PORT", "8765"))
    url = f"http://127.0.0.1:{port}"
    if os.getenv("AGENT_VOLS_NO_BROWSER") != "1":
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    print(f"Agent Vols : {url}  (Ctrl+C pour arrêter)")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()

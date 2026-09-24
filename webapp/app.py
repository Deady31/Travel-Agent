"""App « Départs » : barre de commande, filtres, cartes d'embarquement.

Tourne en local (start.bat) ou sur Vercel (point d'entrée déclaré dans pyproject.toml).
Le serveur ne garde aucun état entre deux requêtes : compatible serverless.
"""

import json
import logging
import os
import re
import time
from datetime import date, datetime
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from agent_vols import airports
from agent_vols.airports import normalize
from agent_vols.parser import parse_command
from agent_vols.places import search_places
from agent_vols.quota import SerpApiAccountQuota, SerpApiQuota
from agent_vols.scoring import rank_offers
from agent_vols.search import SearchParams, run_search
from webapp import auth
from webapp.schemas import LoginIn, ParseIn, RankIn, SearchIn

ROOT = Path(__file__).resolve().parent.parent
STATIC = Path(__file__).parent / "static"
load_dotenv(ROOT / ".env")

SERPAPI_KEY = os.getenv("SERPAPI_KEY", "").strip()
TRAVELPAYOUTS_TOKEN = os.getenv("TRAVELPAYOUTS_TOKEN", "").strip()
DEMO_MODE = os.getenv("AGENT_VOLS_DEMO") == "1"
DEMO_FIXTURE = ROOT / "tests" / "fixtures" / "serpapi_tls_nap.json"
QUOTA = SerpApiAccountQuota(SERPAPI_KEY) if SERPAPI_KEY else SerpApiQuota(ROOT / "data" / "serpapi_quota.json")
LOG_DIR = ROOT / "logs"
LOGIN_FAIL_DELAY = 1.5

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("agent_vols")
app = FastAPI(title="Agent Vols", docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.middleware("http")
async def guard(request: Request, call_next):
    """Mot de passe (si APP_PASSWORD) + revalidation des fichiers pour éviter une vieille version en cache."""
    path = request.url.path
    secret = auth.password()
    problem = auth.config_error()
    if problem:
        return PlainTextResponse(problem, 503)
    if secret and not auth.is_public(path) and not auth.valid_token(request.cookies.get(auth.COOKIE), secret):
        if path.startswith("/api/"):
            return JSONResponse({"detail": "Connexion requise."}, 401)
        return RedirectResponse("/login", 303)
    response = await call_next(request)
    if not path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


# ---------- Pages et fichiers de l'app installable ----------

@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/login")
def login_page() -> FileResponse:
    return FileResponse(STATIC / "login.html")


@app.get("/manifest.webmanifest")
def manifest() -> FileResponse:
    return FileResponse(STATIC / "manifest.webmanifest", media_type="application/manifest+json")


@app.get("/sw.js")
def service_worker() -> FileResponse:
    return FileResponse(STATIC / "sw.js", media_type="application/javascript")


# ---------- Connexion ----------

@app.post("/api/login")
def login(body: LoginIn) -> JSONResponse:
    if not auth.password():
        return JSONResponse({"ok": True})
    if not auth.check_password(body.password):
        time.sleep(LOGIN_FAIL_DELAY)  # freine les essais en rafale
        raise HTTPException(401, "Mot de passe incorrect.")
    response = JSONResponse({"ok": True})
    response.set_cookie(auth.COOKIE, auth.make_token(auth.password()), max_age=auth.SESSION_DAYS * 86400,
                        httponly=True, samesite="lax", secure=auth.on_vercel())
    return response


@app.post("/api/logout")
def logout() -> JSONResponse:
    response = JSONResponse({"ok": True})
    response.delete_cookie(auth.COOKIE)
    return response


# ---------- API ----------

@app.get("/api/config")
def config() -> dict:
    return {
        "origins": airports.origins(),
        "quota_remaining": QUOTA.remaining(),
        "quota_limit": QUOTA.limit,
        "has_live_key": bool(SERPAPI_KEY) or DEMO_MODE,
        "has_cache_token": bool(TRAVELPAYOUTS_TOKEN),
        "demo": DEMO_MODE,
        "auth": bool(auth.password()),
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


def _scrub(text: str) -> str:
    for secret in (SERPAPI_KEY, TRAVELPAYOUTS_TOKEN):
        if secret:
            text = text.replace(secret, "***")
    return text


def _log_raw(raw: dict) -> None:
    """Traçabilité des prix : réponse brute en fichier en local, résumé dans les logs Vercel en ligne."""
    stamp = datetime.now().isoformat(timespec="seconds")
    if auth.on_vercel():
        params = {k: v for k, v in raw.get("search_parameters", {}).items() if k != "api_key"}
        offers = [[f.get("price"), [leg.get("flight_number") for leg in f.get("flights", [])]]
                  for f in raw.get("best_flights", []) + raw.get("other_flights", [])]
        log.info(_scrub(json.dumps({"logged_at": stamp, "search": params, "offers": offers}, ensure_ascii=False)))
        return
    LOG_DIR.mkdir(exist_ok=True)
    with open(LOG_DIR / f"{date.today().isoformat()}.jsonl", "a", encoding="utf-8") as fh:
        fh.write(_scrub(json.dumps({"logged_at": stamp, "raw": raw}, ensure_ascii=False)) + "\n")


def _demo_search(params: SearchParams) -> dict:
    """Rejoue une réponse Google Flights enregistrée : aucun appel réseau, aucun quota."""
    raw = json.loads(DEMO_FIXTURE.read_text(encoding="utf-8"))
    demo_quota = SerpApiQuota(ROOT / "data" / "demo_quota.json", 10**9)
    result = run_search(params, serp_key="demo", tp_token="", quota=demo_quota,
                        fetch_live=lambda *a: raw, today=params.depart_from)
    result["warnings"] = [w for w in result["warnings"] if "Travelpayouts" not in w]
    result["warnings"].insert(0, "Mode démo : données Google Flights enregistrées le 24/09/2026 "
                                 "(TLS → NAP, 28/10 → 01/11), quelle que soit la demande.")
    result["quota_remaining"] = QUOTA.remaining()
    return result


@app.post("/api/search")
def search(body: SearchIn) -> dict:
    if not SERPAPI_KEY and not DEMO_MODE:
        raise HTTPException(400, "Clé SERPAPI_KEY absente (fichier .env ou variables Vercel).")
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
    result.pop("offers_objects", None)
    return result


@app.post("/api/rank")
def rank(body: RankIn) -> dict:
    """Reclasse les offres filtrées renvoyées par le navigateur (prix inchangés, aucun état serveur)."""
    try:
        return rank_offers([o.to_offer() for o in body.offers], body.budget_eur, body.weights,
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

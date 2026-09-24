"""Serveur MCP « Agent Vols » (MVP) — à brancher dans Claude Desktop."""

import json
import os
import re
from datetime import date, datetime
from pathlib import Path

from dotenv import load_dotenv
from mcp.server.mcpserver import MCPServer

from agent_vols.models import Offer
from agent_vols.quota import SerpApiQuota
from agent_vols.scoring import rank_offers
from agent_vols.serpapi_provider import fetch_serpapi, parse_serpapi

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")
SERPAPI_KEY = os.getenv("SERPAPI_KEY", "").strip()
QUOTA = SerpApiQuota(ROOT / "data" / "serpapi_quota.json")
LOG_DIR = ROOT / "logs"
IATA = re.compile(r"^[A-Z]{3}$")

_offers: dict[str, Offer] = {}

mcp = MCPServer(
    name="agent-vols",
    instructions=(
        "Outils de recherche de vols. Ne jamais afficher un prix qui ne vient pas d'un résultat "
        "d'outil. Toujours citer source, fetched_at et search_url."
    ),
)


def _check_iata(code: str, field: str) -> str:
    code = code.strip().upper()
    if not IATA.match(code):
        raise ValueError(f"{field} doit être un code IATA de 3 lettres (reçu : {code!r}).")
    return code


def _check_dates(outbound: str, ret: str) -> None:
    try:
        out_d, ret_d = date.fromisoformat(outbound), date.fromisoformat(ret)
    except ValueError as exc:
        raise ValueError("Dates attendues au format AAAA-MM-JJ.") from exc
    if out_d < date.today():
        raise ValueError(f"La date aller {outbound} est dans le passé.")
    if ret_d <= out_d:
        raise ValueError("La date retour doit être après la date aller.")


def _log(raw: dict) -> None:
    LOG_DIR.mkdir(exist_ok=True)
    text = json.dumps({"logged_at": datetime.now().isoformat(timespec="seconds"), "raw": raw}, ensure_ascii=False)
    if SERPAPI_KEY:
        text = text.replace(SERPAPI_KEY, "***")
    with open(LOG_DIR / f"{date.today().isoformat()}.jsonl", "a", encoding="utf-8") as fh:
        fh.write(text + "\n")


@mcp.tool()
def search_live_flights(origin: str, destination: str, outbound_date: str, return_date: str,
                        adults: int = 1, max_stops: int = 1) -> dict:
    """Recherche EN TEMPS RÉEL de vols aller-retour via Google Flights (SerpApi).

    Quota limité (100 appels/mois) : n'appeler que pour des combinaisons précises.
    Dates au format AAAA-MM-JJ, aéroports en code IATA (ex. TLS, NAP).
    max_stops : 0 = direct uniquement, 1 = une escale max, 2 = deux escales max.
    Le prix est le total aller-retour par passager adulte en EUR ; les détails d'horaires
    concernent le vol aller. Chaque offre a un id à passer ensuite à rank_flights.
    """
    if not SERPAPI_KEY:
        raise ValueError("SERPAPI_KEY absente du fichier .env.")
    origin = _check_iata(origin, "origin")
    destination = _check_iata(destination, "destination")
    _check_dates(outbound_date, return_date)
    if not 1 <= adults <= 9:
        raise ValueError("adults doit être entre 1 et 9.")
    if not 0 <= max_stops <= 2:
        raise ValueError("max_stops doit être 0, 1 ou 2.")

    raw = fetch_serpapi(SERPAPI_KEY, QUOTA, origin, destination, outbound_date, return_date, adults, max_stops)
    _log(raw)
    offers = parse_serpapi(raw)
    _offers.update({o.id: o for o in offers})
    insights = raw.get("price_insights", {})
    return {
        "source": "Google Flights via SerpApi",
        "fetched_at": offers[0].fetched_at if offers else raw.get("search_metadata", {}).get("processed_at"),
        "offers": [o.to_dict() for o in offers],
        "price_insights": {
            "lowest_price": insights.get("lowest_price"),
            "price_level": insights.get("price_level"),
            "typical_price_range": insights.get("typical_price_range"),
        },
        "serpapi_quota_remaining": QUOTA.remaining(),
    }


@mcp.tool()
def rank_flights(offer_ids: list[str], budget_max_eur: float | None = None,
                 weights: dict[str, float] | None = None) -> dict:
    """Classe des offres déjà obtenues et renvoie le top 3 : cheapest, best_balance, most_comfortable.

    offer_ids : identifiants renvoyés par search_live_flights (jamais des prix).
    budget_max_eur : budget max A/R par personne (tolérance +10 %).
    weights : optionnel, clés price / duration / stops / schedule (positifs, renormalisés).
    Seule source autorisée pour les scores. Les prix renvoyés sont ceux de la source, inchangés.
    """
    unknown = [i for i in offer_ids if i not in _offers]
    if unknown:
        raise ValueError(f"Offres inconnues (relancer search_live_flights) : {unknown}")
    return rank_offers([_offers[i] for i in offer_ids], budget_max_eur, weights)


@mcp.tool()
def get_quota() -> dict:
    """Nombre d'appels SerpApi restants ce mois-ci."""
    return {"serpapi_quota_remaining": QUOTA.remaining(), "limit": QUOTA.limit}


if __name__ == "__main__":
    mcp.run()

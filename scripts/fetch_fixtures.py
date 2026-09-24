"""Premier appel réel aux deux sources, sauvegardé comme fixtures de test.

Usage : .venv\\Scripts\\python.exe scripts\\fetch_fixtures.py
Consomme 1 recherche SerpApi (quota 100/mois). Travelpayouts est gratuit.
"""
import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"

ORIGIN, DESTINATION = "TLS", "NAP"
OUTBOUND, RETURN = "2026-10-28", "2026-11-01"


def scrub(data, secrets):
    """Retire toute clé API du JSON avant sauvegarde."""
    text = json.dumps(data, ensure_ascii=False, indent=2)
    for secret in secrets:
        if secret:
            text = text.replace(secret, "***")
    return text


def fetch_serpapi(key):
    params = {
        "engine": "google_flights",
        "departure_id": ORIGIN,
        "arrival_id": DESTINATION,
        "outbound_date": OUTBOUND,
        "return_date": RETURN,
        "type": "1",
        "currency": "EUR",
        "hl": "fr",
        "gl": "fr",
        "api_key": key,
    }
    resp = requests.get("https://serpapi.com/search.json", params=params, timeout=60)
    resp.raise_for_status()
    return resp.json()


def fetch_travelpayouts(token):
    params = {
        "origin": ORIGIN,
        "destination": DESTINATION,
        "departure_at": OUTBOUND[:7],
        "return_at": RETURN[:7],
        "currency": "eur",
        "sorting": "price",
        "limit": 30,
    }
    resp = requests.get(
        "https://api.travelpayouts.com/aviasales/v3/prices_for_dates",
        params=params,
        headers={"X-Access-Token": token},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def main():
    load_dotenv(ROOT / ".env")
    serp_key = os.getenv("SERPAPI_KEY", "").strip()
    tp_token = os.getenv("TRAVELPAYOUTS_TOKEN", "").strip()
    if not serp_key:
        sys.exit("SERPAPI_KEY manquante dans .env")

    FIXTURES.mkdir(parents=True, exist_ok=True)
    secrets = [serp_key, tp_token]

    serp = fetch_serpapi(serp_key)
    if "error" in serp:
        sys.exit(f"SerpApi a renvoyé une erreur : {serp['error']}")
    (FIXTURES / "serpapi_tls_nap.json").write_text(scrub(serp, secrets), encoding="utf-8")
    n_offers = len(serp.get("best_flights", [])) + len(serp.get("other_flights", []))
    print(f"SerpApi OK : {n_offers} offres -> tests/fixtures/serpapi_tls_nap.json")

    if tp_token:
        tp = fetch_travelpayouts(tp_token)
        (FIXTURES / "travelpayouts_tls_nap.json").write_text(scrub(tp, secrets), encoding="utf-8")
        print(f"Travelpayouts OK : {len(tp.get('data', []))} prix en cache -> tests/fixtures/travelpayouts_tls_nap.json")


if __name__ == "__main__":
    main()

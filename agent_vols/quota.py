import json
import time
from datetime import date
from pathlib import Path

import requests


class QuotaExceeded(RuntimeError):
    pass


class SerpApiAccountQuota:
    """Quota réel lu chez SerpApi (account.json, gratuit, ne consomme pas de recherche).

    Fonctionne sans disque : adapté à Vercel. Cache court pour limiter les appels.
    """

    ENDPOINT = "https://serpapi.com/account.json"
    UNKNOWN = 999  # si SerpApi ne répond pas, on laisse passer : SerpApi refusera lui-même au-delà du quota

    def __init__(self, api_key: str, ttl: float = 60, fetch=None, clock=None):
        self._key = api_key
        self._ttl = ttl
        self._fetch = fetch or (lambda: requests.get(self.ENDPOINT, params={"api_key": api_key}, timeout=10).json())
        self._clock = clock or time.monotonic
        self._left: int | None = None
        self._limit = 250
        self._fetched_at = float("-inf")
        self._consumed = 0

    def _refresh(self) -> None:
        if self._clock() - self._fetched_at < self._ttl:
            return
        try:
            data = self._fetch()
            self._left = int(data["total_searches_left"])
            self._limit = int(data.get("searches_per_month", self._limit))
            self._consumed = 0
            self._fetched_at = self._clock()
        except Exception:  # réseau, JSON, champ manquant : on garde la dernière valeur connue
            pass

    @property
    def limit(self) -> int:
        self._refresh()
        return self._limit

    def remaining(self) -> int:
        self._refresh()
        if self._left is None:
            return self.UNKNOWN
        return max(self._left - self._consumed, 0)

    def consume(self) -> None:
        if self.remaining() <= 0:
            raise QuotaExceeded("Quota SerpApi épuisé pour ce mois-ci.")
        self._consumed += 1


class SerpApiQuota:
    """Compteur mensuel local des appels SerpApi (le plan gratuit = 100/mois)."""

    def __init__(self, path: Path, limit: int = 100, month: str | None = None):
        self.path = Path(path)
        self.limit = limit
        self._fixed_month = month

    @property
    def month(self) -> str:
        # Recalculé à chaque appel : un serveur lancé depuis des semaines change bien de mois.
        return self._fixed_month or date.today().strftime("%Y-%m")

    def _used(self) -> int:
        if not self.path.exists():
            return 0
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return data.get("calls", 0) if data.get("month") == self.month else 0

    def remaining(self) -> int:
        return max(self.limit - self._used(), 0)

    def consume(self) -> None:
        used = self._used()
        if used >= self.limit:
            raise QuotaExceeded(f"Quota SerpApi atteint ({self.limit} appels en {self.month}).")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"month": self.month, "calls": used + 1}), encoding="utf-8")

import json
from datetime import date
from pathlib import Path


class QuotaExceeded(RuntimeError):
    pass


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

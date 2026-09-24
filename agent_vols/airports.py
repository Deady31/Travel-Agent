"""Résolution ville -> codes IATA, et infos d'accès aux aéroports de départ."""

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).parent / "data" / "airports.json"
IATA = re.compile(r"^[A-Z]{3}$")


def normalize(text: str) -> str:
    """Minuscules, sans accents, espaces simples : « Athènes » -> « athenes »."""
    stripped = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[\s\-']+", " ", stripped.lower()).strip()


@lru_cache(maxsize=1)
def _data() -> dict:
    return json.loads(DATA.read_text(encoding="utf-8"))


def origins() -> dict[str, dict]:
    return _data()["origins"]


def access_minutes() -> dict[str, int]:
    return {code: info["access_min"] for code, info in origins().items()}


def resolve_destination(text: str) -> dict:
    """Renvoie {"iata": [...], "label": str} ou {"choices": [...]} si ambigu, ou {} si inconnu."""
    raw = text.strip()
    if IATA.match(raw.upper()) and raw.isupper():
        return {"iata": [raw.upper()], "label": raw.upper()}
    key = normalize(raw)
    if key in _data()["ambiguous"]:
        return {"choices": _data()["ambiguous"][key]}
    if key in _data()["destinations"]:
        return {"iata": _data()["destinations"][key], "label": raw.strip().title()}
    return {}


def find_destination_in(text: str) -> tuple[str, dict] | None:
    """Cherche le nom de destination le plus long présent dans une phrase."""
    norm = f" {normalize(text)} "
    names = list(_data()["destinations"]) + list(_data()["ambiguous"])
    for name in sorted(names, key=len, reverse=True):
        if f" {name} " in norm:
            return name, resolve_destination(name)
    for token in re.findall(r"\b[A-Z]{3}\b", text):
        return token, resolve_destination(token)
    return None

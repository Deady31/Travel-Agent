"""Schémas d'entrée de l'API (validation stricte de tout ce qui vient du navigateur)."""

from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from agent_vols.models import Offer
from agent_vols.search import MAX_LIVE_CALLS

Iata = Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]
DateTime = Annotated[str, StringConstraints(pattern=r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")]
IsoDate = Annotated[str, StringConstraints(pattern=r"^\d{4}-\d{2}-\d{2}$")]
Short = Annotated[str, StringConstraints(max_length=80)]


class ParseIn(BaseModel):
    text: str = Field(min_length=1, max_length=300)


class LoginIn(BaseModel):
    password: str = Field(min_length=1, max_length=200)


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


class OfferIn(BaseModel):
    """Offre renvoyée par le navigateur pour être reclassée (le serveur ne garde rien en mémoire)."""

    model_config = ConfigDict(extra="ignore")

    id: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{6,20}$")]
    source: Short
    fetched_at: Short
    origin: Iata
    destination: Iata
    outbound_date: IsoDate
    return_date: IsoDate
    price_eur: float = Field(ge=0, le=100000)
    airlines: list[Short] = Field(min_length=1, max_length=8)
    flight_numbers: list[Short] = Field(min_length=1, max_length=8)
    stops: int = Field(ge=0, le=6)
    duration_min: int = Field(ge=0, le=5000)
    departure_time: DateTime
    arrival_time: DateTime
    search_url: Annotated[str, StringConstraints(max_length=2000)]
    fare_notes: list[Annotated[str, StringConstraints(max_length=300)]] = Field(default_factory=list, max_length=20)

    def to_offer(self) -> Offer:
        data = self.model_dump()
        for key in ("airlines", "flight_numbers", "fare_notes"):
            data[key] = tuple(data[key])
        return Offer(**data)


class RankIn(BaseModel):
    offers: list[OfferIn] = Field(max_length=300)
    budget_eur: float | None = Field(default=None, ge=0, le=20000)
    weights: dict[str, float] | None = None

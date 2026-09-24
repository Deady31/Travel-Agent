from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Offer:
    """Une offre de vol A/R telle que renvoyée par une source, jamais modifiée ensuite."""

    id: str
    source: str
    fetched_at: str
    origin: str
    destination: str
    outbound_date: str
    return_date: str
    price_eur: float
    airlines: tuple[str, ...]
    flight_numbers: tuple[str, ...]
    stops: int
    duration_min: int
    departure_time: str
    arrival_time: str
    search_url: str
    fare_notes: tuple[str, ...]

    def to_dict(self) -> dict:
        return asdict(self)

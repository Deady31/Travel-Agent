import pytest

from agent_vols.quota import QuotaExceeded, SerpApiAccountQuota, SerpApiQuota


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_account_quota_reads_serpapi_and_counts_locally():
    calls = []
    clock = Clock()

    def fetch():
        calls.append(1)
        return {"total_searches_left": 2, "searches_per_month": 250}

    q = SerpApiAccountQuota("k", ttl=60, fetch=fetch, clock=clock)
    assert q.remaining() == 2 and q.limit == 250
    q.consume()
    q.consume()
    with pytest.raises(QuotaExceeded):
        q.consume()
    assert len(calls) == 1  # cache
    clock.t = 61
    assert q.remaining() == 2 and len(calls) == 2


def test_account_quota_survives_serpapi_outage():
    def boom():
        raise ConnectionError()

    q = SerpApiAccountQuota("k", fetch=boom, clock=Clock())
    assert q.remaining() == SerpApiAccountQuota.UNKNOWN
    q.consume()  # ne bloque pas : SerpApi refusera lui-même au-delà du quota


def test_counts_calls_per_month(tmp_path):
    q = SerpApiQuota(tmp_path / "q.json", limit=2, month="2026-09")
    q.consume()
    assert q.remaining() == 1


def test_blocks_when_limit_reached(tmp_path):
    q = SerpApiQuota(tmp_path / "q.json", limit=1, month="2026-09")
    q.consume()
    with pytest.raises(QuotaExceeded):
        q.consume()


def test_resets_on_new_month(tmp_path):
    path = tmp_path / "q.json"
    SerpApiQuota(path, limit=1, month="2026-09").consume()
    assert SerpApiQuota(path, limit=1, month="2026-10").remaining() == 1


def test_month_is_recomputed_when_not_fixed(tmp_path, monkeypatch):
    import agent_vols.quota as quota_mod

    class FakeDate:
        current = "2026-09"

        @classmethod
        def today(cls):
            from datetime import date
            return date.fromisoformat(cls.current + "-15")

    monkeypatch.setattr(quota_mod, "date", FakeDate)
    q = SerpApiQuota(tmp_path / "q.json", limit=1)
    q.consume()
    assert q.remaining() == 0
    FakeDate.current = "2026-10"
    assert q.remaining() == 1


def test_persists_between_instances(tmp_path):
    path = tmp_path / "q.json"
    SerpApiQuota(path, limit=5, month="2026-09").consume()
    assert SerpApiQuota(path, limit=5, month="2026-09").remaining() == 4

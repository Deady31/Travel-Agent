import pytest

from agent_vols.quota import QuotaExceeded, SerpApiQuota


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

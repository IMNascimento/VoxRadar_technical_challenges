"""Testes do rate limit compartilhado, com relógio fake (nunca dorme de verdade)."""

from __future__ import annotations

import pytest

from src.infrastructure.kwai.ratelimit import RateLimiter

MODULE_TIME = "src.infrastructure.kwai.ratelimit.time"


class _FakeClock:
    """Relógio e sono fake: ``sleep`` registra e avança o relógio."""

    def __init__(self, start: float) -> None:
        self.now = start
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.mark.parametrize("min_interval", [0.0, -1.0])
def test_rate_limiter_sem_intervalo_nao_dorme(
    min_interval: float, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock: _FakeClock = _FakeClock(0.0)
    monkeypatch.setattr(MODULE_TIME, clock, raising=True)
    limiter = RateLimiter(min_interval)

    for _ in range(3):
        limiter.wait()

    assert clock.sleeps == []


def test_rate_limiter_primeira_chamada_nao_dorme(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = _FakeClock(start=100.0)
    monkeypatch.setattr(MODULE_TIME, clock, raising=True)
    limiter = RateLimiter(0.5)

    limiter.wait()

    # ``_last`` começa em 0.0: o tempo decorrido já supera o intervalo.
    assert clock.sleeps == []


def test_rate_limiter_dorme_o_faltante_do_intervalo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = _FakeClock(start=100.0)
    monkeypatch.setattr(MODULE_TIME, clock, raising=True)
    limiter = RateLimiter(0.5)
    limiter.wait()

    clock.now = 100.2  # só 0.2s decorreu; deve dormir o faltante (0.3s)
    limiter.wait()
    assert clock.sleeps == [pytest.approx(0.3)]

    clock.now = 101.1  # intervalo já cumprido desde a última chamada: não dorme
    limiter.wait()
    assert clock.sleeps == [pytest.approx(0.3)]

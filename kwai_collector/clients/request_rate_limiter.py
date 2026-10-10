"""Pace sequential requests and interpret server retry delays.

A1_Radar.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from time import monotonic, sleep


def parse_retry_after(
    value: str | None, *, now: datetime | None = None
) -> float | None:
    if not value:
        return None
    try:
        seconds = float(value)
    except ValueError:
        try:
            deadline = parsedate_to_datetime(value)
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=UTC)
            seconds = (deadline - (now or datetime.now(UTC))).total_seconds()
        except (TypeError, ValueError, OverflowError):
            return None
    if not math.isfinite(seconds):
        return None
    return max(0.0, seconds)


def sleep_in_chunks(seconds: float, sleeper: Callable[[float], None] = sleep) -> None:
    while seconds > 0:
        chunk = min(seconds, 60.0)
        sleeper(chunk)
        seconds -= chunk


class RequestRateLimiter:
    def __init__(
        self,
        interval: float,
        *,
        clock: Callable[[], float] = monotonic,
        sleeper: Callable[[float], None] = sleep,
    ) -> None:
        if not math.isfinite(interval) or interval < 0:
            raise ValueError(
                "O intervalo entre requisições deve ser finito e não negativo."
            )
        self.interval = interval
        self.clock = clock
        self.sleeper = sleeper
        self.last_request: float | None = None
        self.not_before = 0.0

    def defer_for(self, seconds: float) -> None:
        if not math.isfinite(seconds) or seconds < 0:
            raise ValueError("O tempo de espera deve ser finito e não negativo.")
        self.not_before = max(self.not_before, self.clock() + seconds)

    def mark_request(self) -> None:
        """Record the send time after any request preparation has finished."""
        self.last_request = self.clock()

    def wait_before_request(self) -> None:
        now = self.clock()
        earliest = self.not_before
        if self.last_request is not None:
            earliest = max(earliest, self.last_request + self.interval)
        remaining = earliest - now
        if remaining > 0:
            sleep_in_chunks(remaining, self.sleeper)
        self.last_request = self.clock()

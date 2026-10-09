"""Relógio do sistema: implementação de :class:`IClockPort`."""

from __future__ import annotations

from datetime import UTC, datetime

from ...application.ports.clock_port import IClockPort
from ...domain.value_objects.iso_timestamp import IsoTimestamp


class SystemClock(IClockPort):
    """Instante atual do sistema, em ISO-8601 UTC."""

    def now(self) -> IsoTimestamp:
        """Carimbo de coleta do instante atual."""
        return IsoTimestamp.from_datetime(datetime.now(tz=UTC))

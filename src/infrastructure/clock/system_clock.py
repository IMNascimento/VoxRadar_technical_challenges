"""Relógio do sistema: implementação de :class:`IClockPort`."""

from __future__ import annotations

from datetime import UTC, datetime

from ...application.ports.clock_port import IClockPort
from ...domain.value_objects.iso_timestamp import IsoTimestamp


class SystemClock(IClockPort):
    """Relógio real: fornece o instante atual do sistema como carimbo ISO-8601 UTC."""

    def now(self) -> IsoTimestamp:
        """Retorna o carimbo de coleta do instante atual."""
        return IsoTimestamp.from_datetime(datetime.now(tz=UTC))

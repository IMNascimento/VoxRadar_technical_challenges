"""Porta do relógio usado no carimbo de coleta."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ...domain.value_objects.iso_timestamp import IsoTimestamp


class IClockPort(ABC):
    """Contrato do relógio: cada execução de caso de uso lê um único carimbo."""

    @abstractmethod
    def now(self) -> IsoTimestamp:
        """Instante atual, em ISO-8601 UTC."""

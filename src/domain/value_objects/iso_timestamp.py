"""Timestamp ISO-8601 UTC usado no carimbo de coleta do contrato."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime

from ..exceptions.domain_exceptions import InvalidValueError

_ISO_UTC_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
_ISO_UTC_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


@dataclass(frozen=True)
class IsoTimestamp:
    """Carimbo de coleta em ISO-8601 UTC (sufixo ``Z``)."""

    value: str

    def __post_init__(self) -> None:
        if _ISO_UTC_PATTERN.fullmatch(self.value) is None:
            raise InvalidValueError(f"timestamp ISO-8601 UTC inválido: {self.value!r}")

    @classmethod
    def from_datetime(cls, moment: datetime) -> IsoTimestamp:
        """Converte um instante com fuso para UTC, com precisão de segundos."""
        return cls(moment.astimezone(UTC).strftime(_ISO_UTC_FORMAT))

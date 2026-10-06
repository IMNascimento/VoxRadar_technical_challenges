"""Timestamp ISO-8601 UTC usado no carimbo de coleta do contrato."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..exceptions import KwaiCollectorError

_ISO_UTC_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")


@dataclass(frozen=True)
class IsoTimestamp:
    """Carimbo de coleta em ISO-8601 UTC (sufixo ``Z``)."""

    value: str

    def __post_init__(self) -> None:
        if _ISO_UTC_PATTERN.fullmatch(self.value) is None:
            raise KwaiCollectorError(f"timestamp ISO-8601 UTC inválido: {self.value!r}")

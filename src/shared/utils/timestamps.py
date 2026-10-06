"""Conversão de timestamps para o formato ISO-8601 UTC do contrato."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from .coercion import as_int_scalar


def now_iso() -> str:
    """Carimbo de data/hora atual em ISO-8601 UTC (sufixo ``Z``)."""
    return _to_iso(datetime.now(tz=UTC))


def iso_from_timestamp_ms(value: Any) -> str | None:
    """Converte um timestamp em milissegundos para ISO-8601 UTC.

    Args:
        value: valor cru do Kwai (número, string numérica ou inválido).

    Returns:
        O instante em ISO-8601 com sufixo ``Z``, ou ``None`` se ausente,
        não numérico ou não positivo.
    """
    milliseconds = as_int_scalar(value)
    if milliseconds is None or milliseconds <= 0:
        return None
    try:
        return _to_iso(datetime.fromtimestamp(milliseconds / 1000, tz=UTC))
    except (OverflowError, OSError, ValueError):  # pragma: no cover - defensivo
        return None


def _to_iso(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

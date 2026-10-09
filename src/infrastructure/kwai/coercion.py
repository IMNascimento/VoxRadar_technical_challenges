"""Coerção de valores crus vindos do JSON do Kwai: escalares e timestamps em ms."""

from __future__ import annotations

from datetime import UTC, datetime

from ...domain.value_objects.iso_timestamp import IsoTimestamp

# Tipos escalares aceitos; ``bool`` é rejeitado à parte (subclasse de ``int``).
_INT_SCALAR_TYPES: tuple[type[int], type[float], type[str]] = (int, float, str)


def as_int_scalar(value: object) -> int | None:
    """Converte um escalar cru em ``int``, sem inventar valores.

    Args:
        value: valor vindo do JSON do Kwai.

    Returns:
        O inteiro correspondente, ou ``None`` para ``None``, ``bool``,
        tipo não escalar ou valor não conversível.
    """
    if value is None or isinstance(value, bool):
        return None
    if not isinstance(value, _INT_SCALAR_TYPES):
        return None
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def iso_from_timestamp_ms(value: object) -> str | None:
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
        moment = datetime.fromtimestamp(milliseconds / 1000, tz=UTC)
    except (OverflowError, OSError, ValueError):  # pragma: no cover - defensivo
        return None
    return IsoTimestamp.from_datetime(moment).value

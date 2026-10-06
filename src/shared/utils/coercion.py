"""Coerção de escalares crus vindos do JSON do Kwai."""

from __future__ import annotations

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
    except (TypeError, ValueError):
        return None

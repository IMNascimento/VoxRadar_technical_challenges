"""Exceções da camada de infraestrutura do coletor."""

from __future__ import annotations

from ..domain.exceptions import KwaiCollectorError


class KwaiTransportError(KwaiCollectorError):
    """Falha de transporte na comunicação com o Kwai."""


class UnexpectedResponseError(KwaiCollectorError):
    """Resposta do Kwai fora do formato esperado."""

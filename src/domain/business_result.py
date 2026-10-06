"""Validação do campo ``result`` das respostas do Kwai."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .exceptions import KwaiApiError


def ensure_business_success(
    body: Mapping[str, Any],
    *,
    default_message: str,
    source: str | None = None,
) -> None:
    """Garante que a resposta não sinalize erro de negócio.

    O Kwai responde HTTP 200 mesmo em falhas, sinalizando no campo ``result``
    (``1`` = sucesso; campo ausente é tolerado). ``default_message`` é usada
    quando o corpo não traz ``error_msg``. ``source`` identifica a rota
    chamada: quando presente, a mensagem termina em ``em {source}``.

    Args:
        body: corpo JSON decodificado da resposta.
        default_message: mensagem padrão quando ``error_msg`` está ausente.
        source: rota/origem usada apenas na composição da mensagem.

    Raises:
        KwaiApiError: se ``result`` estiver presente e for diferente de ``1``.
    """
    result = body.get("result")
    if result is None or result == 1:
        return
    message = body.get("error_msg") or default_message
    suffix = f" em {source}" if source else ""
    raise KwaiApiError(f"{message} (result={result}){suffix}", result=result)

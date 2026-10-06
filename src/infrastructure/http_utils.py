"""Utilitários HTTP compartilhados pelos adapters do Kwai."""

from __future__ import annotations

from typing import Any

import httpx

from .exceptions import UnexpectedResponseError


def decode_json_dict(response: httpx.Response) -> dict[str, Any]:
    """Decodifica o corpo da resposta como um objeto JSON.

    Args:
        response: resposta HTTP recebida.

    Returns:
        O corpo JSON decodificado.

    Raises:
        UnexpectedResponseError: se o corpo não for JSON ou não for um objeto.
    """
    try:
        body = response.json()
    except ValueError as exc:
        raise UnexpectedResponseError(f"resposta não-JSON de {response.url}") from exc
    if not isinstance(body, dict):
        raise UnexpectedResponseError(f"corpo JSON inesperado de {response.url}")
    return body

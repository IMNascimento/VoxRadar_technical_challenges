"""Utilitários HTTP compartilhados pelos adapters do Kwai."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from .exceptions import UnexpectedResponseError

_Operation = TypeVar("_Operation", bound=Callable[..., Any])

# Valores de ``pcursor`` com que o Kwai sinaliza o fim da paginação.
_END_CURSORS: frozenset[str] = frozenset({"no_more", "nomore", "-1", "0"})
# Status HTTP transitórios: justificam nova tentativa; os demais 4xx/5xx não.
RETRYABLE_STATUS: frozenset[int] = frozenset({429, 500, 502, 503, 504})


class TransientHttpError(Exception):
    """Falha transitória que aciona o retry; o cliente a converte antes de sair dele."""


def is_transient_failure(exc: Exception) -> bool:
    """Indica se a falha de uma requisição pode passar numa nova tentativa.

    Transitórias: falha de transporte (conexão, timeout), status de
    :data:`RETRYABLE_STATUS` e corpo fora do formato (ex.: HTML de CDN/WAF).
    Status permanente (ex.: 400, 403, 404) não é repetido.
    """
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in RETRYABLE_STATUS
    return isinstance(exc, httpx.TransportError | UnexpectedResponseError)


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


def read_object_list(payload: dict[str, Any], field: str, *, source: str) -> list[dict[str, Any]]:
    """Valida uma lista de objetos antes de entregar a página ao caso de uso.

    Args:
        payload: objeto JSON recebido da API.
        field: campo da lista; ausente ou nulo mantém a tolerância existente.
        source: rota usada para localizar o erro.

    Returns:
        Objetos da lista, na ordem original.

    Raises:
        UnexpectedResponseError: se a lista ou um item tiver tipo inesperado.
    """
    items = payload.get(field)
    if items is None:
        return []
    if not isinstance(items, list):
        raise UnexpectedResponseError(f"{source}: {field} deve ser uma lista JSON")
    objects: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise UnexpectedResponseError(f"{source}: {field}[{index}] deve ser um objeto JSON")
        objects.append(item)
    return objects


def read_cursor(payload: dict[str, Any], *, source: str) -> str:
    """Lê o cursor sem transformar estruturas JSON inválidas em strings.

    Args:
        payload: objeto JSON recebido da API.
        source: rota usada para localizar o erro.

    Returns:
        Cursor textual; ausente, nulo ou sentinela de fim do Kwai vira vazio.

    Raises:
        UnexpectedResponseError: se o cursor não for uma string ou inteiro.
    """
    value = payload.get("pcursor")
    if value is None:
        return ""
    if isinstance(value, bool) or not isinstance(value, str | int):
        raise UnexpectedResponseError(f"{source}: pcursor deve ser uma string ou inteiro")
    cursor = str(value or "")
    return "" if cursor in _END_CURSORS else cursor


def transient_retry(
    max_retries: int, *, on: tuple[type[BaseException], ...]
) -> Callable[[_Operation], _Operation]:
    """Decorator de retry com backoff exponencial para falhas transitórias.

    Args:
        max_retries: tentativas **extras** depois da primeira (``0`` desliga o retry).
        on: tipos de exceção que justificam uma nova tentativa; qualquer outra
            (ex.: erro de negócio) sobe na hora.

    Returns:
        O decorator; esgotadas as tentativas, a última exceção é relançada.
    """
    return retry(
        reraise=True,
        stop=stop_after_attempt(max_retries + 1),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=8.0),
        retry=retry_if_exception_type(on),
    )

"""Adapter da API web do Kwai (busca) sobre httpx.

Implementa :class:`~src.application.ports.SearchApiPort` e concentra o I/O da
web: sessão httpx, rate limit, retry com backoff e payload de busca. As
postagens de perfil **não** passam por aqui: vêm da API móvel anônima
(:mod:`src.infrastructure.mobile_client`).
"""

from __future__ import annotations

from typing import Any

import httpx

from ..application.models import Post
from ..application.ports import SearchApiPort
from ..config import Settings
from ..domain.business_result import ensure_business_success
from ..domain.constants import BASE_URL
from ..domain.value_objects.iso_timestamp import IsoTimestamp
from ..shared.logging_config import get_logger
from ..shared.utils.ratelimit import RateLimiter
from .exceptions import KwaiTransportError
from .http_utils import decode_json_dict, transient_retry
from .mapping import parse_feeds

logger = get_logger("http")

# Erros transitórios que justificam retry.
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}

SEARCH_PATH = "/rest/o/w/pwa/v2/search/word/outer"
# Origem fixa que o site envia no payload de busca (capturada do front).
SEARCH_REQUEST_SOURCE = 1102


class _TransientHttpError(Exception):
    """Erro transitório interno, usado para acionar o retry do tenacity."""


class KwaiWebAdapter(SearchApiPort):
    """Acesso HTTP à API web do Kwai (busca por palavra-chave)."""

    def __init__(self, settings: Settings) -> None:
        """Inicializa a sessão httpx com os cabeçalhos do site.

        Args:
            settings: configuração do coletor (timeout, retry, UA, delay).
        """
        self._settings = settings
        self._rate = RateLimiter(settings.request_delay)
        headers = {
            "User-Agent": settings.user_agent,
            "Accept": "application/json, text/plain, */*",
            "Origin": BASE_URL,
            "Referer": f"{BASE_URL}/",
        }
        self._client = httpx.Client(
            base_url=BASE_URL,
            headers=headers,
            timeout=settings.http_timeout,
            follow_redirects=True,
        )

    def close(self) -> None:
        """Encerra a sessão HTTP."""
        self._client.close()

    def search_posts(self, keyword: str, count: int, *, collected_at: IsoTimestamp) -> list[Post]:
        """Busca postagens de uma palavra-chave (uma requisição).

        Args:
            keyword: palavra-chave da busca.
            count: itens pedidos ao endpoint (já limitado pelo caso de uso).
            collected_at: carimbo de coleta aplicado a todas as postagens.

        Returns:
            As postagens do lote, na ordem do feed.
        """
        body = self._post_json(SEARCH_PATH, self._build_search_payload(keyword, count))
        return parse_feeds(body.get("feeds"), collected_at=collected_at.value)

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Faz um POST JSON e devolve o corpo decodificado.

        Raises:
            KwaiTransportError: se a requisição falhar no transporte/status.
            UnexpectedResponseError: se o corpo não for um objeto JSON.
            KwaiApiError: se o Kwai sinalizar erro de negócio.
        """
        response = self._post_with_retry(path, payload)
        body = decode_json_dict(response)
        ensure_business_success(
            body,
            default_message="erro de negócio da API do Kwai",
            source=path,
        )
        return body

    def _post_with_retry(self, path: str, payload: dict[str, Any]) -> httpx.Response:
        """Faz o POST JSON com rate limit e retry de falhas transitórias."""
        retrying = transient_retry(
            self._settings.max_retries, on=(_TransientHttpError, httpx.TransportError)
        )
        try:
            return retrying(self._post_once)(path, payload)
        except (httpx.HTTPError, _TransientHttpError) as exc:
            raise KwaiTransportError(f"POST {path} falhou: {exc}") from exc

    def _post_once(self, path: str, payload: dict[str, Any]) -> httpx.Response:
        """Uma tentativa: status transitório vira ``_TransientHttpError`` (aciona o retry)."""
        self._rate.wait()
        logger.debug("POST %s", path)
        response = self._client.post(path, json=payload)
        if response.status_code in _RETRYABLE_STATUS:
            logger.warning(
                "resposta transitória %s em %s; tentando novamente", response.status_code, path
            )
            raise _TransientHttpError(str(response.status_code))
        response.raise_for_status()
        return response

    @staticmethod
    def _build_search_payload(keyword: str, count: int) -> dict[str, Any]:
        return {
            "searchWord": keyword,
            "count": count,
            "fromUser": False,
            "mobile": True,
            "pcursor": 0,
            "request_source": SEARCH_REQUEST_SOURCE,
            "url": f"{BASE_URL}/discover",
        }

"""Adapter da API web do Kwai (busca e perfil) sobre httpx.

Implementa :class:`~src.application.ports.SearchApiPort` e
:class:`~src.application.ports.ProfileApiPort` e concentra o I/O da
web: sessão httpx, rate limit, retry com backoff, payload de busca e avaliação
do estado SSR do perfil.
"""

from __future__ import annotations

from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ..application.models import Postagem
from ..application.ports import ProfileApiPort, SearchApiPort
from ..config import Settings
from ..domain.business_result import ensure_business_success
from ..domain.constants import BASE_URL
from ..domain.value_objects.identifiers import Handle
from ..domain.value_objects.iso_timestamp import IsoTimestamp
from ..shared.logging_config import get_logger
from ..shared.utils.ratelimit import RateLimiter
from .exceptions import KwaiTransportError, UnexpectedResponseError
from .http_utils import decode_json_dict
from .mapping import parse_feed
from .nuxt import evaluate_feeds_data

logger = get_logger("http")

# Erros transitórios que justificam retry.
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}

SEARCH_PATH = "/rest/o/w/pwa/v2/search/word/outer"
PROFILE_PATH = "/@{handle}"
# Origem fixa que o site envia no payload de busca (capturada do front).
SEARCH_REQUEST_SOURCE = 1102


class _TransientHttpError(Exception):
    """Erro transitório interno, usado para acionar o retry do tenacity."""


class KwaiWebAdapter(SearchApiPort, ProfileApiPort):
    """Acesso HTTP à API web do Kwai (busca e perfil)."""

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

    def search_posts(
        self, keyword: str, count: int, *, collected_at: IsoTimestamp
    ) -> list[Postagem]:
        """Busca postagens de uma palavra-chave (uma requisição).

        Args:
            keyword: palavra-chave da busca.
            count: itens pedidos ao endpoint (já limitado pelo caso de uso).
            collected_at: carimbo de coleta aplicado a todas as postagens.

        Returns:
            As postagens do lote, na ordem do feed.
        """
        body = self._post_json(SEARCH_PATH, self._build_search_payload(keyword, count))
        return self._parse_feeds(body.get("feeds"), collected_at=collected_at.value)

    def profile_posts(self, handle: Handle, *, collected_at: IsoTimestamp) -> list[Postagem]:
        """Coleta as postagens embutidas no estado SSR do perfil.

        Args:
            handle: conta validada, sem ``@`` (ex.: ``Handle("perfil")``).
            collected_at: carimbo de coleta aplicado a todas as postagens.

        Returns:
            As postagens da primeira página embutida no HTML.
        """
        html = self._get_text(PROFILE_PATH.format(handle=handle.value))
        feeds_data = evaluate_feeds_data(html)
        return self._parse_feeds(feeds_data.feeds, collected_at=collected_at.value)

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Faz um POST JSON e devolve o corpo decodificado.

        Raises:
            KwaiTransportError: se a requisição falhar no transporte/status.
            UnexpectedResponseError: se o corpo não for um objeto JSON.
            KwaiApiError: se o Kwai sinalizar erro de negócio.
        """
        response = self._request_with_retry("POST", path, json_body=payload)
        body = decode_json_dict(response)
        ensure_business_success(
            body,
            default_message="erro de negócio da API do Kwai",
            source=path,
        )
        return body

    def _get_text(self, path: str) -> str:
        """Faz um GET de HTML e devolve o corpo como texto (SSR do perfil)."""
        response = self._request_with_retry(
            "GET", path, extra_headers={"Accept": "text/html,application/xhtml+xml"}
        )
        return response.text

    def _request_with_retry(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """Executa a requisição com rate limit e retry de falhas transitórias."""
        attempts = self._settings.max_retries + 1

        @retry(
            reraise=True,
            stop=stop_after_attempt(attempts),
            wait=wait_exponential(multiplier=0.5, min=0.5, max=8.0),
            retry=retry_if_exception_type((_TransientHttpError, httpx.TransportError)),
        )
        def _do() -> httpx.Response:
            self._rate.wait()
            logger.debug("%s %s", method, path)
            response = self._client.request(method, path, json=json_body, headers=extra_headers)
            if response.status_code in _RETRYABLE_STATUS:
                logger.warning(
                    "resposta transitória %s em %s; tentando novamente",
                    response.status_code,
                    path,
                )
                raise _TransientHttpError(str(response.status_code))
            response.raise_for_status()
            return response

        try:
            return _do()
        except (httpx.HTTPError, _TransientHttpError) as exc:
            raise KwaiTransportError(f"{method} {path} falhou: {exc}") from exc

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

    @staticmethod
    def _parse_feeds(feeds: Any, *, collected_at: str) -> list[Postagem]:
        """Mapeia os feeds de um corpo/SSR; itens não-dict ou sem URL são ignorados com aviso."""
        posts: list[Postagem] = []
        for feed in feeds or []:
            if not isinstance(feed, dict):
                continue
            try:
                posts.append(parse_feed(feed, collected_at=collected_at))
            except UnexpectedResponseError as exc:
                logger.warning("feed ignorado: %s", exc)
        return posts

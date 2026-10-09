"""Cliente HTTP da API web do Kwai: sessão, rate limit, retry e erro de negócio."""

from __future__ import annotations

from typing import Any

import httpx

from ....config.settings import Settings
from ....shared.logging.logging_config import get_logger
from ..business_result import ensure_business_success
from ..exceptions import KwaiTransportError
from ..http_utils import RETRYABLE_STATUS, TransientHttpError, decode_json_dict, transient_retry
from ..ratelimit import RateLimiter

logger = get_logger("http")

# Origem do site, onde a API web responde. Coincide com a base das URLs públicas
# (``post_urls.BASE_URL``), mas é o host de transporte e pode mudar sozinho.
WEB_ORIGIN: str = "https://www.kwai.com"


class KwaiWebClient:
    """Sessão httpx com os cabeçalhos do site, rate limit e retry de falhas transitórias."""

    def __init__(self, settings: Settings) -> None:
        """Inicializa a sessão httpx com os cabeçalhos do site.

        Args:
            settings: configuração do coletor (timeout, retry, UA, delay).
        """
        self._rate = RateLimiter(settings.request_delay)
        self._post_once_with_retry = transient_retry(
            settings.max_retries, on=(TransientHttpError, httpx.TransportError)
        )(self._post_once)
        headers = {
            "User-Agent": settings.user_agent,
            "Accept": "application/json, text/plain, */*",
            "Origin": WEB_ORIGIN,
            "Referer": f"{WEB_ORIGIN}/",
        }
        self._client = httpx.Client(
            base_url=WEB_ORIGIN,
            headers=headers,
            timeout=settings.http_timeout,
            follow_redirects=True,
        )

    def close(self) -> None:
        """Encerra a sessão HTTP."""
        self._client.close()

    def post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
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
        try:
            return self._post_once_with_retry(path, payload)
        except (httpx.HTTPError, TransientHttpError) as exc:
            raise KwaiTransportError(f"POST {path} falhou: {exc}") from exc

    def _post_once(self, path: str, payload: dict[str, Any]) -> httpx.Response:
        """Uma tentativa: status transitório vira ``TransientHttpError`` (aciona o retry)."""
        self._rate.wait()
        logger.debug("POST %s", path)
        response = self._client.post(path, json=payload)
        if response.status_code in RETRYABLE_STATUS:
            logger.warning(
                "resposta transitória %s em %s; tentando novamente", response.status_code, path
            )
            raise TransientHttpError(str(response.status_code))
        response.raise_for_status()
        return response

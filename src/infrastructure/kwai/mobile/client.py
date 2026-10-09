"""Cliente da API móvel anônima do Kwai: sessão, rate limit, assinatura e gateways.

A requisição é **anônima** (sem login, sem cookies) e assinada **apenas com o
``sig``** (:mod:`src.infrastructure.kwai.mobile.signature`), que cobre query e
corpo. Há uma **escada de fallback entre gateways** equivalentes (mesma rota e
mesma assinatura); se todos falharem, a escada inteira é repetida com backoff.
O contexto de cada rota (query e corpo) é decidido pelo adapter.
"""

from __future__ import annotations

from typing import Any

import httpx

from ....config.settings import Settings
from ....shared.logging.logging_config import get_logger
from ..business_result import ensure_business_success
from ..exceptions import KwaiTransportError, UnexpectedResponseError
from ..http_utils import decode_json_dict, transient_retry
from ..ratelimit import RateLimiter
from .app_identity import APP_USER_AGENT
from .signature import compute_sig

logger = get_logger("mobile")

COMMENT_HOST = "https://api.kwai-pro.com"
# Gateways equivalentes (mesma rota e mesma assinatura); tenta na ordem.
COMMENT_FALLBACK_HOSTS: tuple[str, ...] = (
    "https://api1-us.kwai-pro.com",
    "https://api2-us.kwaipros.com",
)
COMMENT_HOSTS: tuple[str, ...] = (COMMENT_HOST, *COMMENT_FALLBACK_HOSTS)


class MobileApiClient:
    """Transporte da API móvel: sessão, rate limit, assinatura ``sig`` e escada de gateways."""

    def __init__(self, settings: Settings) -> None:
        """Inicializa a sessão httpx anônima.

        Args:
            settings: configuração do coletor (timeout, delay do rate limit e retries).
        """
        self._rate = RateLimiter(settings.request_delay)
        self._client = httpx.Client(
            timeout=settings.http_timeout,
            headers={"User-Agent": APP_USER_AGENT, "Accept": "application/json"},
        )
        self._post_with_retry = transient_retry(settings.max_retries, on=(KwaiTransportError,))(
            self._post_through_ladder
        )

    def close(self) -> None:
        """Encerra a sessão HTTP."""
        self._client.close()

    def post(self, path: str, *, query: dict[str, str], body: dict[str, str]) -> dict[str, Any]:
        """Assina query e corpo e POSTa pela escada, repetindo-a com backoff se todos falharem.

        Só falha de transporte é repetida (``max_retries`` rodadas extras da
        escada); erro de negócio (``result != 1``) sobe na hora.

        Raises:
            KwaiTransportError: se todos os gateways falharem em todas as rodadas.
            KwaiApiError: se o Kwai sinalizar erro de negócio.
        """
        signed_body = {**body, "sig": compute_sig({**query, **body})}
        return self._post_with_retry(path=path, query=query, body=signed_body)

    def _post_through_ladder(
        self, *, path: str, query: dict[str, str], body: dict[str, str]
    ) -> dict[str, Any]:
        """Uma rodada: POSTa no primeiro gateway que responder (mesma rota e assinatura).

        Um corpo inválido (HTML de CDN/WAF, por exemplo) conta como falha
        daquele gateway e a escada segue para o próximo host.

        Raises:
            KwaiTransportError: se todos os gateways falharem nesta rodada.
            KwaiApiError: se o Kwai sinalizar erro de negócio.
        """
        self._rate.wait()
        last_error: Exception | None = None
        for host in COMMENT_HOSTS:
            try:
                response = self._client.post(host + path, params=query, data=body)
                response.raise_for_status()
                payload = decode_json_dict(response)
            except (httpx.HTTPError, UnexpectedResponseError) as exc:
                # Falha transitória do gateway (transporte ou corpo inválido): tenta o próximo.
                last_error = exc
                logger.warning("gateway %s falhou (%s); tentando o próximo", host, exc)
                continue
            ensure_business_success(
                payload,
                default_message="erro de negócio da API móvel do Kwai",
                source=path,
            )
            return payload
        raise KwaiTransportError(f"todos os gateways falharam: {last_error}") from last_error

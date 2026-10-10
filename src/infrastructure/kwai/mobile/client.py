"""Cliente da API móvel anônima do Kwai: sessão, rate limit, assinatura e gateways.

A requisição é **anônima** (sem login, sem cookies) e assinada **apenas com o
``sig``** (:mod:`src.infrastructure.kwai.mobile.signature`), que cobre query e
corpo. Há uma **escada de fallback entre gateways** equivalentes (mesma rota e
mesma assinatura); se todos falharem e ao menos uma falha for transitória, a
escada inteira é repetida com backoff.
O contexto de cada rota (query e corpo) é decidido pelo adapter.
"""

from __future__ import annotations

from typing import Any

import httpx

from ....config.settings import Settings
from ....shared.logging.logging_config import get_logger
from ..business_result import ensure_business_success
from ..exceptions import KwaiTransportError, UnexpectedResponseError
from ..http_utils import (
    TransientHttpError,
    decode_json_dict,
    is_transient_failure,
    transient_retry,
)
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
        self._post_with_retry = transient_retry(settings.max_retries, on=(TransientHttpError,))(
            self._post_through_ladder
        )

    def close(self) -> None:
        """Encerra a sessão HTTP."""
        self._client.close()

    def post(self, path: str, *, query: dict[str, str], body: dict[str, str]) -> dict[str, Any]:
        """Assina query e corpo e envia o POST pela escada de gateways.

        Um status de erro ou um corpo inválido em um gateway passa para o próximo.
        Se todos falharem e ao menos uma falha for transitória, a escada inteira é
        repetida com backoff (até ``max_retries`` rodadas extras); se todas forem
        permanentes (ex.: 403), não há nova rodada. Erro de negócio
        (``result != 1``) sobe na hora, sem trocar de gateway.

        Args:
            path: rota da API móvel (ex.: ``/rest/o/comment/list/v2``).
            query: parâmetros de query, incluídos na assinatura.
            body: campos do corpo, incluídos na assinatura.

        Returns:
            O corpo JSON da resposta bem-sucedida.

        Raises:
            KwaiTransportError: se todos os gateways falharem (após as rodadas,
                quando a falha for transitória).
            KwaiApiError: se o Kwai sinalizar erro de negócio.
        """
        signed_body = {**body, "sig": compute_sig({**query, **body})}
        try:
            return self._post_with_retry(path=path, query=query, body=signed_body)
        except TransientHttpError as exc:
            # O sinal interno de retry não é a causa: preserva a falha do último gateway.
            raise KwaiTransportError(str(exc)) from exc.__cause__

    def _post_through_ladder(
        self, *, path: str, query: dict[str, str], body: dict[str, str]
    ) -> dict[str, Any]:
        """Uma rodada: POSTa no primeiro gateway que responder (mesma rota e assinatura).

        Cada gateway respeita o rate limit. Um corpo inválido (HTML de CDN/WAF,
        por exemplo) ou um status de erro conta como falha daquele gateway e a
        escada segue para o próximo host.

        Raises:
            TransientHttpError: se todos falharem e ao menos uma falha for transitória.
            KwaiTransportError: se todos falharem de forma permanente (ex.: 403).
            KwaiApiError: se o Kwai sinalizar erro de negócio.
        """
        failures: list[Exception] = []
        for host in COMMENT_HOSTS:
            self._rate.wait()
            try:
                response = self._client.post(host + path, params=query, data=body)
                response.raise_for_status()
                payload = decode_json_dict(response)
            except (httpx.HTTPError, UnexpectedResponseError) as exc:
                failures.append(exc)
                logger.warning("gateway %s falhou (%s); tentando o próximo", host, exc)
                continue
            ensure_business_success(
                payload,
                default_message="erro de negócio da API móvel do Kwai",
                source=path,
            )
            return payload
        last_error = failures[-1]
        message = f"todos os gateways falharam: {last_error}"
        if any(is_transient_failure(exc) for exc in failures):
            raise TransientHttpError(message) from last_error
        raise KwaiTransportError(message) from last_error

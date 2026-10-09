"""Adapter da busca web do Kwai: implementa :class:`ISearchApiPort` sobre o cliente web.

Conhece o endpoint de busca e o formato do payload; a sessão, o rate limit e o
retry ficam no :class:`KwaiWebClient`. As postagens de perfil **não** passam por
aqui: vêm da API móvel anônima (:mod:`src.infrastructure.kwai.mobile`).
"""

from __future__ import annotations

from typing import Any

from ....application.ports.search_api_port import ISearchApiPort
from ....domain.entities.post import Post
from ....domain.value_objects.iso_timestamp import IsoTimestamp
from ....shared.logging.logging_config import get_logger
from ..mapping import parse_feeds
from .client import WEB_ORIGIN, KwaiWebClient

logger = get_logger("http")

SEARCH_PATH = "/rest/o/w/pwa/v2/search/word/outer"
# Origem fixa que o site envia no payload de busca (capturada do front).
SEARCH_REQUEST_SOURCE = 1102
# O endpoint "outer" de busca não usa cursor e limita o lote a ~50 itens.
SEARCH_MAX_COUNT = 50


class KwaiWebAdapter(ISearchApiPort):
    """Busca por palavra-chave na API web do Kwai."""

    def __init__(self, client: KwaiWebClient) -> None:
        """Inicializa o adapter.

        Args:
            client: cliente da API web, dono da sessão HTTP.
        """
        self._client = client

    def search_posts(self, keyword: str, *, limit: int, collected_at: IsoTimestamp) -> list[Post]:
        """Busca postagens de uma palavra-chave (uma requisição).

        Args:
            keyword: palavra-chave da busca.
            limit: itens desejados; o lote pedido ao endpoint não passa de
                :data:`SEARCH_MAX_COUNT`.
            collected_at: carimbo de coleta aplicado a todas as postagens.

        Returns:
            As postagens do lote, na ordem do feed.

        Raises:
            KwaiTransportError: se a requisição falhar no transporte/status.
            UnexpectedResponseError: se o corpo não for um objeto JSON.
            KwaiApiError: se o Kwai sinalizar erro de negócio.
        """
        payload = _build_search_payload(keyword, _request_count(limit))
        body = self._client.post_json(SEARCH_PATH, payload)
        return parse_feeds(body.get("feeds"), collected_at=collected_at.value)


def _request_count(limit: int) -> int:
    """Itens pedidos ao endpoint: o ``limit``, sem passar do lote máximo da busca."""
    if limit > SEARCH_MAX_COUNT:
        logger.warning(
            "endpoint de busca limita o lote a %d itens por palavra-chave; usando count=%d",
            SEARCH_MAX_COUNT,
            SEARCH_MAX_COUNT,
        )
    return min(limit, SEARCH_MAX_COUNT)


def _build_search_payload(keyword: str, count: int) -> dict[str, Any]:
    return {
        "searchWord": keyword,
        "count": count,
        "fromUser": False,
        "mobile": True,
        "pcursor": 0,
        "request_source": SEARCH_REQUEST_SOURCE,
        "url": f"{WEB_ORIGIN}/discover",
    }

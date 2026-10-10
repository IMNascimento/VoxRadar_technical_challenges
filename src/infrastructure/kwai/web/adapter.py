"""Adapter da busca web do Kwai: implementa :class:`ISearchApiPort` sobre o cliente web.

Conhece o endpoint de busca e o formato do payload; a sessão, o rate limit e o
retry ficam no :class:`KwaiWebClient`. As postagens de perfil **não** passam por
aqui: vêm da API móvel anônima (:mod:`src.infrastructure.kwai.mobile`).
"""

from __future__ import annotations

from typing import Any

from ....application.dtos.pages import SearchPage
from ....application.ports.search_api_port import ISearchApiPort
from ....domain.value_objects.iso_timestamp import IsoTimestamp
from ..mapping import parse_feeds
from .client import WEB_ORIGIN, KwaiWebClient

SEARCH_PATH = "/rest/o/w/pwa/v2/search/word/outer"
# Origem fixa que o site envia no payload de busca (capturada do front).
SEARCH_REQUEST_SOURCE = 1102
# Itens por página da busca; o ``pcursor`` do corpo é o deslocamento da página.
SEARCH_PAGE_SIZE = 50


class KwaiWebAdapter(ISearchApiPort):
    """Implementa :class:`ISearchApiPort` sobre o endpoint de busca da API web do Kwai."""

    def __init__(self, client: KwaiWebClient) -> None:
        """Inicializa o adapter.

        Args:
            client: cliente da API web, dono da sessão HTTP.
        """
        self._client = client

    def search_page(
        self, keyword: str, *, offset: int, limit: int, collected_at: IsoTimestamp
    ) -> SearchPage:
        """Busca uma página de postagens de uma palavra-chave (uma requisição).

        Args:
            keyword: palavra-chave da busca.
            offset: deslocamento da página, enviado como ``pcursor``.
            limit: itens desejados; a página pedida não passa de
                :data:`SEARCH_PAGE_SIZE`.
            collected_at: carimbo de coleta aplicado a todas as postagens.

        Returns:
            As postagens da página, na ordem do feed, e o deslocamento da
            próxima página.

        Raises:
            KwaiTransportError: se a requisição falhar no transporte/status.
            UnexpectedResponseError: se o corpo não for um objeto JSON ou ``feeds`` não for uma lista.
            KwaiApiError: se o Kwai sinalizar erro de negócio.
        """
        count = min(limit, SEARCH_PAGE_SIZE)
        body = self._client.post_json(SEARCH_PATH, _build_search_payload(keyword, count, offset))
        posts = parse_feeds(body.get("feeds"), collected_at=collected_at.value)
        return SearchPage(posts=posts, next_offset=offset + count)


def _build_search_payload(keyword: str, count: int, offset: int) -> dict[str, Any]:
    return {
        "searchWord": keyword,
        "count": count,
        "fromUser": False,
        "mobile": True,
        "pcursor": offset,
        "request_source": SEARCH_REQUEST_SOURCE,
        "url": f"{WEB_ORIGIN}/discover",
    }

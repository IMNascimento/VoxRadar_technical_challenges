"""Porta de busca de postagens por palavra-chave."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ...domain.value_objects.iso_timestamp import IsoTimestamp
from ..dtos.pages import SearchPage


class ISearchApiPort(ABC):
    """Contrato de busca de postagens por palavra-chave — agnóstico de transporte."""

    @abstractmethod
    def search_page(
        self, keyword: str, *, offset: int, limit: int, collected_at: IsoTimestamp
    ) -> SearchPage:
        """Busca uma página de postagens de uma palavra-chave (uma requisição por chamada).

        A página começa em ``offset`` e pede até ``limit`` itens; o adapter pode
        pedir menos quando o endpoint limitar o tamanho da página. Decidir o fim
        da paginação é responsabilidade do caso de uso.

        Raises:
            ExternalServiceError: se o serviço externo falhar no transporte, no
                formato da resposta ou com erro de negócio.
        """

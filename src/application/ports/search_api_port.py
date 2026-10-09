"""Porta de busca de postagens por palavra-chave."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ...domain.entities.post import Post
from ...domain.value_objects.iso_timestamp import IsoTimestamp


class ISearchApiPort(ABC):
    """Contrato de busca de postagens por palavra-chave — agnóstico de transporte."""

    @abstractmethod
    def search_posts(self, keyword: str, *, limit: int, collected_at: IsoTimestamp) -> list[Post]:
        """Busca até ``limit`` postagens de uma palavra-chave (uma requisição por chamada).

        O adapter pode devolver menos que ``limit`` quando o endpoint limitar o lote.

        Raises:
            ExternalServiceError: se o serviço externo falhar no transporte, no
                formato da resposta ou com erro de negócio.
        """

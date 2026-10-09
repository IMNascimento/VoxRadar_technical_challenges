"""Caso de uso: busca de postagens por palavra-chave (API web)."""

from __future__ import annotations

from ...domain.entities.post import Post
from ...domain.exceptions.domain_exceptions import KwaiCollectorError
from ...domain.services.identity import unique_posts
from ...domain.services.post_ordering import order_posts
from ...shared.logging.logging_config import COLLECTOR_LOGGER_NAME, get_logger
from ..dtos.collection_result import CollectionResult
from ..dtos.commands import SearchCommand
from ..exceptions import reraise_with_partial
from ..ports.clock_port import IClockPort
from ..ports.search_api_port import ISearchApiPort

logger = get_logger(COLLECTOR_LOGGER_NAME)


class SearchPosts:
    """Coleta postagens relacionadas a uma ou mais palavras-chave."""

    def __init__(self, api: ISearchApiPort, clock: IClockPort) -> None:
        """Inicializa o caso de uso.

        Args:
            api: porta de busca da API web do Kwai.
            clock: relógio do carimbo de coleta.
        """
        self._api = api
        self._clock = clock

    def execute(self, command: SearchCommand) -> CollectionResult[Post]:
        """Faz uma requisição por palavra-chave e deduplica o resultado.

        Args:
            command: palavras-chave, teto do resultado final (após dedupe) e
                ordenação aplicada após o limite.

        Returns:
            As postagens únicas, na ordem de coleta ou decrescente pela contagem
            escolhida. Uma falha vira ``error``, com o parcial já coletado.
        """
        try:
            posts = self._collect(command)
        except KwaiCollectorError as exc:
            return CollectionResult.failed("posts", exc, Post)
        return CollectionResult("posts", tuple(posts))

    def _collect(self, command: SearchCommand) -> list[Post]:
        collected_at = self._clock.now()
        posts: list[Post] = []
        unique = unique_posts()
        for keyword in command.keywords:
            logger.info("buscando por %r (limite=%d)", keyword, command.limit)
            try:
                batch = self._api.search_posts(
                    keyword, limit=command.limit, collected_at=collected_at
                )
            except KwaiCollectorError as exc:
                reraise_with_partial(exc, order_posts(posts, command.sort_by))
            posts.extend(unique.filter(batch))
            if len(posts) >= command.limit:
                break
        logger.info("busca retornou %d postagens únicas", len(posts))
        return order_posts(posts[: command.limit], command.sort_by)

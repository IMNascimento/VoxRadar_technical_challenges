"""Caso de uso: busca de postagens por palavra-chave (API web)."""

from __future__ import annotations

from ..domain.exceptions import InvalidInputError, KwaiCollectorError
from ..domain.identity import post_dedup_key
from ..domain.value_objects.iso_timestamp import IsoTimestamp
from ..shared.logging_config import COLLECTOR_LOGGER_NAME, get_logger
from ..shared.utils.timestamps import now_iso
from .exceptions import reraise_with_partial
from .models import Post
from .ports import SearchApiPort
from .post_ordering import order_posts, validate_sort_by

logger = get_logger(COLLECTOR_LOGGER_NAME)

# O endpoint "outer" de busca não usa cursor e limita o lote a ~50 itens.
SEARCH_MAX_COUNT = 50


class SearchPosts:
    """Coleta postagens relacionadas a uma ou mais palavras-chave."""

    def __init__(self, api: SearchApiPort) -> None:
        """Inicializa o caso de uso.

        Args:
            api: porta de busca da API web do Kwai.
        """
        self._api = api

    def execute(
        self, keywords: list[str], *, limit: int = 20, sort_by: str | None = None
    ) -> list[Post]:
        """Faz uma requisição por palavra-chave e deduplica o resultado.

        Args:
            keywords: palavras-chave da busca (ao menos uma).
            limit: teto do resultado final, após dedupe.
            sort_by: likes, comments, shares ou views; ordena após o limite.

        Returns:
            As postagens únicas, na ordem de coleta ou decrescente pela contagem escolhida.

        Raises:
            InvalidInputError: se ``keywords`` estiver vazio.
            CollectionInterruptedError: se uma palavra-chave falhar depois de as
                anteriores já terem devolvido postagens; o coletado vai em ``partial``.
            KwaiCollectorError: se a falha vier na primeira palavra-chave.
        """
        if not keywords:
            raise InvalidInputError("informe ao menos uma palavra-chave")
        metric = validate_sort_by(sort_by)
        count = self._request_count(limit)
        collected_at = IsoTimestamp(now_iso())
        unique: dict[str, Post] = {}
        for keyword in keywords:
            logger.info("buscando por %r (count=%d)", keyword, count)
            try:
                batch = self._api.search_posts(keyword, count, collected_at=collected_at)
            except KwaiCollectorError as exc:
                reraise_with_partial(exc, order_posts(list(unique.values()), metric))
            for post in batch:
                unique.setdefault(post_dedup_key(post.id, post.url), post)
            if len(unique) >= limit:
                break
        logger.info("busca retornou %d postagens únicas", len(unique))
        return order_posts(list(unique.values())[:limit], metric)

    @staticmethod
    def _request_count(limit: int) -> int:
        if limit > SEARCH_MAX_COUNT:
            logger.warning(
                "endpoint de busca limita o lote a %d itens por palavra-chave; usando count=%d",
                SEARCH_MAX_COUNT,
                SEARCH_MAX_COUNT,
            )
        return max(1, min(limit, SEARCH_MAX_COUNT))

"""Caso de uso: postagens de um usuário (API móvel anônima, paginada)."""

from __future__ import annotations

from itertools import chain

from ...domain.entities.post import Post
from ...domain.exceptions.domain_exceptions import KwaiCollectorError
from ...domain.services.identity import unique_posts
from ...domain.services.pagination import iter_pages
from ...domain.services.post_ordering import order_posts
from ...domain.value_objects.identifiers import UserId
from ...domain.value_objects.iso_timestamp import IsoTimestamp
from ...shared.logging.logging_config import COLLECTOR_LOGGER_NAME, get_logger
from ..dtos.commands import ProfileCollectionCommand
from ..exceptions import reraise_with_partial
from ..ports.clock_port import IClockPort
from ..ports.profile_api_port import IProfileApiPort

logger = get_logger(COLLECTOR_LOGGER_NAME)


class CollectUserPosts:
    """Coleta as postagens de um usuário pela API móvel anônima."""

    def __init__(self, api: IProfileApiPort, clock: IClockPort) -> None:
        """Inicializa o caso de uso.

        Args:
            api: porta de leitura do perfil na API móvel.
            clock: relógio do carimbo de coleta.
        """
        self._api = api
        self._clock = clock

    def execute(self, command: ProfileCollectionCommand) -> list[Post]:
        """Resolve o handle, pagina o feed e deduplica as postagens.

        O feed exige o id numérico, então o handle é resolvido antes; o
        ``limit`` conta **postagens únicas** e a decisão de fim de paginação
        fica no domínio, via :func:`iter_pages`.

        Args:
            command: conta já normalizada, teto opcional de postagens únicas e
                ordenação aplicada após o limite.

        Returns:
            As postagens únicas, na ordem do feed ou decrescente pela contagem escolhida.

        Raises:
            CollectionInterruptedError: se a coleta falhar depois de já ter
                postagens; o que foi coletado vai em ``partial``.
            KwaiCollectorError: se a falha vier antes da primeira postagem.
        """
        handle = command.handle
        logger.info("coletando postagens de @%s", handle.value)
        collected_at = self._clock.now()
        user_id = self._api.resolve_user(handle)
        posts = self._collect_pages(user_id, collected_at=collected_at, command=command)
        logger.info("usuário @%s: %d postagens coletadas", handle.value, len(posts))
        return order_posts(posts, command.sort_by)

    def _collect_pages(
        self,
        user_id: UserId,
        *,
        collected_at: IsoTimestamp,
        command: ProfileCollectionCommand,
    ) -> list[Post]:
        """Percorre as páginas do ``pcursor`` e deduplica as postagens."""
        pages = iter_pages(
            lambda cursor: self._api.fetch_profile_page(
                user_id, cursor=cursor, collected_at=collected_at
            ),
            is_empty=lambda page: not page.posts,
            source="perfil",
        )
        posts: list[Post] = []
        unique = unique_posts()
        try:
            for post in unique.filter(chain.from_iterable(page.posts for page in pages)):
                posts.append(post)
                if command.limit is not None and len(posts) >= command.limit:
                    break
        except KwaiCollectorError as exc:
            reraise_with_partial(exc, order_posts(posts, command.sort_by))
        return posts

"""Caso de uso: postagens de um usuário (API móvel anônima, paginada)."""

from __future__ import annotations

from itertools import chain

from ..domain.exceptions import KwaiCollectorError
from ..domain.identity import normalize_handle, post_dedup_key
from ..domain.value_objects.identifiers import UserId
from ..domain.value_objects.iso_timestamp import IsoTimestamp
from ..shared.logging_config import COLLECTOR_LOGGER_NAME, get_logger
from ..shared.utils.timestamps import now_iso
from .exceptions import reraise_with_partial
from .models import Post
from .pagination import iter_pages
from .ports import ProfileApiPort
from .post_ordering import PostSortBy, order_posts, validate_sort_by

logger = get_logger(COLLECTOR_LOGGER_NAME)

# Itens por página do feed de perfil (o app pede 30; 30 é respeitado).
USER_POSTS_PAGE_SIZE = 30


class CollectUserPosts:
    """Coleta as postagens de um usuário pela API móvel anônima."""

    def __init__(self, api: ProfileApiPort) -> None:
        """Inicializa o caso de uso.

        Args:
            api: porta de leitura do perfil na API móvel.
        """
        self._api = api

    def execute(
        self, user: str, *, limit: int | None = None, sort_by: str | None = None
    ) -> list[Post]:
        """Resolve o handle, pagina o feed e deduplica as postagens.

        O feed exige o id numérico, então o handle é resolvido antes; o
        ``limit`` conta **postagens únicas** e a decisão de fim de paginação
        fica no domínio, via :meth:`Cursor.is_end`.

        Args:
            user: conta do usuário (ex.: ``@perfil`` ou ``perfil``).
            limit: teto opcional de postagens únicas.
            sort_by: likes, comments, shares ou views; ordena após o limite.

        Returns:
            As postagens únicas, na ordem do feed ou decrescente pela contagem escolhida.

        Raises:
            InvalidInputError: se a conta for inválida.
            CollectionInterruptedError: se a coleta falhar depois de já ter
                postagens; o que foi coletado vai em ``partial``.
            KwaiCollectorError: se a falha vier antes da primeira postagem.
        """
        handle = normalize_handle(user)
        metric = validate_sort_by(sort_by)
        logger.info("coletando postagens de @%s", handle.value)
        collected_at = IsoTimestamp(now_iso())
        user_id = self._api.resolve_user(handle)
        posts = self._collect_pages(user_id, collected_at=collected_at, limit=limit, sort_by=metric)
        logger.info("usuário @%s: %d postagens coletadas", handle.value, len(posts))
        return order_posts(posts, metric)

    def _collect_pages(
        self,
        user_id: UserId,
        *,
        collected_at: IsoTimestamp,
        limit: int | None,
        sort_by: PostSortBy | None,
    ) -> list[Post]:
        """Percorre as páginas do ``pcursor`` e deduplica as postagens."""
        pages = iter_pages(
            lambda cursor: self._api.fetch_profile_page(
                user_id, cursor=cursor, count=USER_POSTS_PAGE_SIZE, collected_at=collected_at
            ),
            is_empty=lambda page: not page.posts,
            source="perfil",
        )
        posts: list[Post] = []
        seen: set[str] = set()
        try:
            for post in chain.from_iterable(page.posts for page in pages):
                key = post_dedup_key(post.id, post.url)
                if key in seen:
                    continue
                seen.add(key)
                posts.append(post)
                if limit is not None and len(posts) >= limit:
                    break
        except KwaiCollectorError as exc:
            reraise_with_partial(exc, order_posts(posts, sort_by))
        return posts

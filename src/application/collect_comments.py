"""Caso de uso: comentários de uma postagem (API móvel anônima)."""

from __future__ import annotations

from collections.abc import Iterator
from itertools import chain

from ..domain.exceptions import KwaiCollectorError
from ..domain.identity import comment_dedup_key, extract_photo_id
from ..domain.value_objects.identifiers import CommentId, PhotoId
from ..domain.value_objects.iso_timestamp import IsoTimestamp
from ..shared.logging_config import COLLECTOR_LOGGER_NAME, get_logger
from ..shared.utils.timestamps import now_iso
from .exceptions import RepeatedCursorError, reraise_with_partial
from .models import Comment, ExpandedComment
from .pagination import iter_pages
from .ports import CommentApiPort, RootComment

logger = get_logger(COLLECTOR_LOGGER_NAME)

# Itens por página pedidos ao gateway (sem ``count`` ele devolve 5; 20, 50 e 100 são respeitados).
COMMENTS_PAGE_SIZE = 50
# Itens por página da sublista de respostas (o gateway respeita até 100).
SUBLIST_PAGE_SIZE = 100


def _expanded_root(root: RootComment) -> ExpandedComment:
    """Raiz no formato expandido, com o total de respostas que a API declara."""
    return ExpandedComment(
        **root.comentario.model_dump(), respostas_total=root.respostas_declaradas
    )


def _warn_reply_count(root: RootComment, collected: int) -> None:
    """Compara o total declarado com o efetivamente entregue, sem inferir a causa."""
    declared = root.respostas_declaradas
    if declared is not None and declared >= 0 and declared != collected:
        logger.warning(
            "respostas da raiz %s: declaradas=%d, coletadas=%d; causa não determinada",
            root.comentario.id or "sem id",
            declared,
            collected,
        )


class CollectComments:
    """Coleta os comentários de uma postagem a partir do link."""

    def __init__(self, api: CommentApiPort) -> None:
        """Inicializa o caso de uso.

        Args:
            api: porta de leitura da API móvel de comentários.
        """
        self._api = api

    def execute(
        self, post_url: str, *, limit: int | None = None, with_replies: bool = False
    ) -> list[Comment]:
        """Percorre as páginas do ``pcursor`` e deduplica os comentários.

        O ``limit`` conta **itens crus de raiz** devolvidos pela API (antes do
        dedupe), como na coleta original; a decisão de fim de paginação fica no
        domínio (via :meth:`Cursor.is_end`), não no adapter.

        Com ``with_replies``, cada raiz é seguida das suas respostas numa lista
        plana: a resposta aponta para a raiz via ``parent_id`` e a raiz traz
        ``respostas_total`` com o total que a API **declara** (que pode ser maior
        que o número de respostas efetivamente coletadas). Sem a opção, a saída é
        idêntica à coleta de raízes. Uma raiz cuja sublista entra em laço de
        cursor é registrada no log e as demais seguem.

        Args:
            post_url: link da postagem (``.../@perfil/video/<id>``).
            limit: teto opcional de itens crus de raiz a buscar.
            with_replies: se ``True``, coleta também as respostas de cada raiz.

        Returns:
            Os comentários únicos, na ordem de coleta (raiz seguida das respostas
            quando ``with_replies``).

        Raises:
            InvalidInputError: se a URL não tiver um id de postagem válido.
            CollectionInterruptedError: se a coleta falhar depois de já ter
                comentários; o que foi coletado vai em ``partial``.
            KwaiCollectorError: se a falha vier antes do primeiro comentário.
        """
        photo_id = extract_photo_id(post_url)
        logger.info("coletando comentários da postagem %s", photo_id.value)
        collected_at = IsoTimestamp(now_iso())
        roots = self._collect_roots(
            photo_id, post_url=post_url, collected_at=collected_at, limit=limit
        )
        comments: list[Comment] = [root.comentario for root in roots]
        if with_replies:
            comments = self._expand_replies(
                photo_id, roots, post_url=post_url, collected_at=collected_at
            )
        logger.info("postagem %s: %d comentários coletados", photo_id.value, len(comments))
        return comments

    def _collect_roots(
        self, photo_id: PhotoId, *, post_url: str, collected_at: IsoTimestamp, limit: int | None
    ) -> list[RootComment]:
        roots: list[RootComment] = []
        seen: set[str] = set()
        try:
            for root in self._iter_raw_roots(
                photo_id, post_url=post_url, collected_at=collected_at, limit=limit
            ):
                comment = root.comentario
                key = comment_dedup_key(comment.id, comment.autor.id, comment.texto)
                if key not in seen:
                    seen.add(key)
                    roots.append(root)
        except KwaiCollectorError as exc:
            reraise_with_partial(exc, [root.comentario for root in roots])
        return roots

    def _iter_raw_roots(
        self, photo_id: PhotoId, *, post_url: str, collected_at: IsoTimestamp, limit: int | None
    ) -> Iterator[RootComment]:
        """Itens crus de raiz, na ordem da API; para ao atingir o ``limit`` cru."""
        pages = iter_pages(
            lambda cursor: self._api.fetch_page(
                photo_id,
                cursor=cursor,
                count=COMMENTS_PAGE_SIZE,
                postagem_url=post_url,
                collected_at=collected_at,
            ),
            is_empty=lambda page: not page.comments,
            source="raízes",
        )
        for fetched, root in enumerate(chain.from_iterable(page.comments for page in pages), 1):
            yield root
            if limit is not None and fetched >= limit:
                return

    def _expand_replies(
        self,
        photo_id: PhotoId,
        roots: list[RootComment],
        *,
        post_url: str,
        collected_at: IsoTimestamp,
    ) -> list[Comment]:
        expanded: list[Comment] = []
        seen: set[str] = set()
        for index, root in enumerate(roots):
            comment = root.comentario
            seen.add(comment_dedup_key(comment.id, comment.autor.id, comment.texto))
            expanded.append(_expanded_root(root))
            if comment.id is None or not root.respostas_declaradas:
                _warn_reply_count(root, 0)
                continue
            start = len(expanded)
            try:
                expanded.extend(
                    self._collect_replies(
                        photo_id,
                        comment.id,
                        post_url=post_url,
                        collected_at=collected_at,
                        seen=seen,
                    )
                )
            except KwaiCollectorError as exc:
                _warn_reply_count(root, len(expanded) - start)
                # as raízes que ainda não tiveram as respostas buscadas não se perdem
                expanded.extend(_expanded_root(pending) for pending in roots[index + 1 :])
                reraise_with_partial(exc, expanded)
            _warn_reply_count(root, len(expanded) - start)
        return expanded

    def _collect_replies(
        self,
        photo_id: PhotoId,
        root_id: str,
        *,
        post_url: str,
        collected_at: IsoTimestamp,
        seen: set[str],
    ) -> Iterator[Comment]:
        """Respostas de uma raiz, uma a uma (o que já saiu não se perde numa falha)."""
        pages = iter_pages(
            lambda cursor: self._api.fetch_sub_page(
                photo_id,
                root_comment_id=CommentId(root_id),
                cursor=cursor,
                count=SUBLIST_PAGE_SIZE,
                postagem_url=post_url,
                collected_at=collected_at,
            ),
            is_empty=lambda page: not page.comments,
            source=f"sublista da raiz {root_id}",
        )
        try:
            for sub in chain.from_iterable(page.comments for page in pages):
                comment = sub.comentario
                key = comment_dedup_key(comment.id, comment.autor.id, comment.texto)
                if key in seen:
                    continue
                seen.add(key)
                yield ExpandedComment(
                    **comment.model_dump(),
                    parent_id=root_id,
                    reply_to_id=sub.reply_to_id,
                    reply_to_usuario=sub.reply_to_usuario,
                )
        except RepeatedCursorError as exc:
            logger.warning("respostas da raiz %s truncadas: %s", root_id, exc)

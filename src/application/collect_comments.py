"""Caso de uso: comentários de uma postagem (API móvel anônima)."""

from __future__ import annotations

from ..domain.exceptions import KwaiCollectorError
from ..domain.identity import comment_dedup_key, extract_photo_id
from ..domain.value_objects.cursor import Cursor
from ..domain.value_objects.identifiers import CommentId, PhotoId
from ..domain.value_objects.iso_timestamp import IsoTimestamp
from ..shared.logging_config import COLLECTOR_LOGGER_NAME, get_logger
from ..shared.utils.timestamps import now_iso
from .models import Comentario, ComentarioExpandido
from .ports import CommentApiPort, RootComment

logger = get_logger(COLLECTOR_LOGGER_NAME)

# Itens por página pedidos ao gateway (20 é o default; 50 e 100 são respeitados).
COMMENTS_PAGE_SIZE = 50
# Itens por página da sublista de respostas (o gateway respeita até 100).
SUBLIST_PAGE_SIZE = 100


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
    ) -> list[Comentario]:
        """Percorre as páginas do ``pcursor`` e deduplica os comentários.

        O ``limit`` conta **itens crus de raiz** devolvidos pela API (antes do
        dedupe), como na coleta original; a decisão de fim de paginação fica no
        domínio (via :meth:`Cursor.is_end`), não no adapter.

        Com ``with_replies``, cada raiz é seguida das suas respostas numa lista
        plana: a resposta aponta para a raiz via ``parent_id`` e a raiz traz
        ``respostas_total`` com o total que a API **declara** (que pode ser maior
        que o número de respostas efetivamente coletadas). Sem a opção, a saída é
        idêntica à coleta de raízes.

        Args:
            post_url: link da postagem (``.../@perfil/video/<id>``).
            limit: teto opcional de itens crus de raiz a buscar.
            with_replies: se ``True``, coleta também as respostas de cada raiz.

        Returns:
            Os comentários únicos, na ordem de coleta (raiz seguida das respostas
            quando ``with_replies``).

        Raises:
            InvalidInputError: se a URL não tiver um id de postagem válido.
            KwaiCollectorError: se a API repetir o cursor da sublista de uma raiz.
        """
        photo_id = extract_photo_id(post_url)
        logger.info("coletando comentários da postagem %s", photo_id.value)
        collected_at = IsoTimestamp(now_iso())
        roots = self._collect_roots(
            photo_id, post_url=post_url, collected_at=collected_at, limit=limit
        )
        comments: list[Comentario] = [root.comentario for root in roots]
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
        seen_cursors: set[str] = set()
        cursor = Cursor("")
        fetched = 0
        while True:
            page = self._api.fetch_page(
                photo_id,
                cursor=cursor,
                count=COMMENTS_PAGE_SIZE,
                postagem_url=post_url,
                collected_at=collected_at,
            )
            for root in page.comments:
                fetched += 1
                comment = root.comentario
                key = comment_dedup_key(comment.id, comment.autor.id, comment.texto)
                if key not in seen:
                    seen.add(key)
                    roots.append(root)
                if limit is not None and fetched >= limit:
                    return roots
            next_cursor = page.next_cursor
            if not page.comments or next_cursor.is_end():
                return roots
            if next_cursor.value in seen_cursors:
                raise KwaiCollectorError(f"cursor de raízes repetido: {next_cursor.value!r}")
            seen_cursors.add(next_cursor.value)
            cursor = next_cursor

    def _expand_replies(
        self,
        photo_id: PhotoId,
        roots: list[RootComment],
        *,
        post_url: str,
        collected_at: IsoTimestamp,
    ) -> list[Comentario]:
        expanded: list[Comentario] = []
        seen: set[str] = set()
        for root in roots:
            comment = root.comentario
            key = comment_dedup_key(comment.id, comment.autor.id, comment.texto)
            seen.add(key)
            expanded.append(
                ComentarioExpandido(
                    **comment.model_dump(),
                    respostas_total=root.respostas_declaradas,
                )
            )
            if comment.id is None or not root.respostas_declaradas:
                continue
            expanded.extend(
                self._collect_replies(
                    photo_id,
                    comment.id,
                    post_url=post_url,
                    collected_at=collected_at,
                    seen=seen,
                )
            )
        return expanded

    def _collect_replies(
        self,
        photo_id: PhotoId,
        root_id: str,
        *,
        post_url: str,
        collected_at: IsoTimestamp,
        seen: set[str],
    ) -> list[Comentario]:
        replies: list[Comentario] = []
        seen_cursors: set[str] = set()
        cursor = Cursor("")
        while True:
            page = self._api.fetch_sub_page(
                photo_id,
                root_comment_id=CommentId(root_id),
                cursor=cursor,
                count=SUBLIST_PAGE_SIZE,
                postagem_url=post_url,
                collected_at=collected_at,
            )
            for sub in page.comments:
                comment = sub.comentario
                key = comment_dedup_key(comment.id, comment.autor.id, comment.texto)
                if key in seen:
                    continue
                seen.add(key)
                replies.append(
                    ComentarioExpandido(
                        **comment.model_dump(),
                        parent_id=root_id,
                        reply_to_id=sub.reply_to_id,
                        reply_to_usuario=sub.reply_to_usuario,
                    )
                )
            next_cursor = page.next_cursor
            if not page.comments or next_cursor.is_end():
                return replies
            if next_cursor.value in seen_cursors:
                raise KwaiCollectorError(
                    f"cursor de sublista repetido na raiz {root_id}: {next_cursor.value!r}"
                )
            seen_cursors.add(next_cursor.value)
            cursor = next_cursor

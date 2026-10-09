"""Caso de uso: versões de comentários de uma postagem (raízes e respostas)."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from itertools import chain

from ...domain.entities.comment import Comment, ExpandedComment
from ...domain.exceptions.domain_exceptions import KwaiCollectorError, RepeatedCursorError
from ...domain.services.identity import UniqueItems, unique_comments
from ...domain.services.replies import declares_replies, replies_diverge
from ...domain.value_objects.identifiers import CommentId
from ...domain.value_objects.iso_timestamp import IsoTimestamp
from ...domain.value_objects.post_reference import PostReference
from ...shared.logging.logging_config import COLLECTOR_LOGGER_NAME, get_logger
from ..dtos.collection_result import CollectionResult
from ..dtos.commands import CommentCollectionCommand
from ..dtos.pages import RootComment
from ..exceptions import reraise_with_partial
from ..pagination import iter_pages
from ..ports.clock_port import IClockPort
from ..ports.comment_api_port import ICommentApiPort
from ..ports.use_case_ports import ICollectCommentVersionsPort

logger = get_logger(COLLECTOR_LOGGER_NAME)


@dataclass(frozen=True)
class _CommentScope:
    """Postagem alvo e carimbo de coleta, comuns a todas as páginas de uma coleta."""

    post: PostReference
    collected_at: IsoTimestamp


def _expanded_root(root: RootComment) -> ExpandedComment:
    """Raiz no formato expandido, com o total de respostas que a API declara."""
    return ExpandedComment.from_comment(root.comment, respostas_total=root.declared_replies)


def _warn_reply_count(root: RootComment, collected: int) -> None:
    """Avisa quando o total declarado diverge do entregue, sem inferir a causa."""
    if replies_diverge(root.declared_replies, collected):
        logger.warning(
            "respostas da raiz %s: declaradas=%d, coletadas=%d; causa não determinada",
            root.comment.id or "sem id",
            root.declared_replies,
            collected,
        )


class _CommentReader:
    """Mecânica de raízes e expansão, sem escolher versões de saída."""

    def __init__(self, api: ICommentApiPort) -> None:
        """Inicializa o leitor.

        Args:
            api: porta de leitura da API móvel de comentários.
        """
        self._api = api

    def collect_roots(self, scope: _CommentScope, *, limit: int | None) -> list[RootComment]:
        """Raízes únicas até o ``limit`` cru; uma falha preserva as já coletadas."""
        roots: list[RootComment] = []
        unique = unique_comments()
        try:
            for root in self._iter_raw_roots(scope, limit=limit):
                if unique.add(root.comment):
                    roots.append(root)
        except KwaiCollectorError as exc:
            reraise_with_partial(exc, [root.comment for root in roots])
        return roots

    def expand_replies(self, scope: _CommentScope, roots: list[RootComment]) -> list[Comment]:
        """Lista plana de raízes e respostas; uma falha preserva também as raízes pendentes.

        Todas as raízes são registradas antes da expansão: uma resposta com a
        identidade de uma raiz (mesmo posterior) é descartada, e a raiz fica.
        """
        expanded: list[Comment] = []
        unique = unique_comments()
        for root in roots:
            unique.add(root.comment)
        for index, root in enumerate(roots):
            expanded.append(_expanded_root(root))
            start = len(expanded)
            try:
                expanded.extend(self._collect_replies(scope, root, unique))
            except KwaiCollectorError as exc:
                _warn_reply_count(root, len(expanded) - start)
                expanded.extend(_expanded_root(pending) for pending in roots[index + 1 :])
                reraise_with_partial(exc, expanded)
            _warn_reply_count(root, len(expanded) - start)
        return expanded

    def _iter_raw_roots(self, scope: _CommentScope, *, limit: int | None) -> Iterator[RootComment]:
        """Itens crus de raiz, na ordem da API; para ao atingir o ``limit`` cru."""
        pages = iter_pages(
            lambda cursor: self._api.fetch_page(
                scope.post, cursor=cursor, collected_at=scope.collected_at
            ),
            is_empty=lambda page: not page.comments,
            source="raízes",
        )
        for fetched, root in enumerate(chain.from_iterable(page.comments for page in pages), 1):
            yield root
            if limit is not None and fetched >= limit:
                return

    def _collect_replies(
        self, scope: _CommentScope, root: RootComment, unique: UniqueItems[Comment]
    ) -> Iterator[Comment]:
        """Respostas de uma raiz, uma a uma (o que já saiu não se perde numa falha).

        Sem id não há como consultar a sublista; sem respostas declaradas não há
        o que expandir.
        """
        root_id = root.comment.id
        if root_id is None or not declares_replies(root.declared_replies):
            return
        pages = iter_pages(
            lambda cursor: self._api.fetch_sub_page(
                scope.post,
                root_comment_id=CommentId(root_id),
                cursor=cursor,
                collected_at=scope.collected_at,
            ),
            is_empty=lambda page: not page.comments,
            source=f"sublista da raiz {root_id}",
        )
        try:
            for sub in chain.from_iterable(page.comments for page in pages):
                if not unique.add(sub.comment):
                    continue
                yield ExpandedComment.from_comment(
                    sub.comment,
                    parent_id=root_id,
                    reply_to_id=sub.reply_to_id,
                    reply_to_usuario=sub.reply_to_usuario,
                )
        except RepeatedCursorError as exc:
            logger.warning("respostas da raiz %s truncadas: %s", root_id, exc)


class CollectCommentVersions(ICollectCommentVersionsPort):
    """Entrega versões independentes, sem buscar raízes novamente para expandir."""

    def __init__(self, api: ICommentApiPort, clock: IClockPort) -> None:
        """Inicializa o caso de uso.

        Args:
            api: porta de leitura da API móvel de comentários.
            clock: relógio do carimbo de coleta.
        """
        self._reader = _CommentReader(api)
        self._clock = clock

    def execute(self, command: CommentCollectionCommand) -> Iterator[CollectionResult[Comment]]:
        """Entrega raízes antes da expansão; identifica a falha pela etapa executada.

        O ``limit`` conta raízes cruas, antes da deduplicação; respostas não o
        consomem. Uma falha vira um resultado com ``error`` e o parcial da etapa.
        """
        post = command.post
        scope = _CommentScope(post, self._clock.now())
        try:
            roots = self._reader.collect_roots(scope, limit=command.limit)
        except KwaiCollectorError as exc:
            yield CollectionResult.failed("comments", exc, Comment, post=post)
            return
        if command.versions.has_roots:
            items = tuple(root.comment for root in roots)
            yield CollectionResult("comments", items, post=post)
        if not command.versions.has_replies:
            return
        try:
            expanded = self._reader.expand_replies(scope, roots)
        except KwaiCollectorError as exc:
            yield CollectionResult.failed("comments-replies", exc, Comment, post=post)
            return
        yield CollectionResult("comments-replies", tuple(expanded), post=post)

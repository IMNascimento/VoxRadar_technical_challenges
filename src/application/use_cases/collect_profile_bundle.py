"""Coleta sequencial de posts e versões de comentários, isolada por postagem."""

from __future__ import annotations

from collections.abc import Iterator

from ...domain.entities.comment import Comment
from ...domain.entities.post import Post
from ...domain.exceptions.domain_exceptions import KwaiCollectorError
from ...domain.services.post_urls import reference_post
from ..dtos.collection_result import CollectionResult
from ..dtos.commands import CommentCollectionCommand, ProfileCollectionCommand
from ..ports.clock_port import IClockPort
from ..ports.comment_api_port import ICommentApiPort
from ..ports.profile_api_port import IProfileApiPort
from .collect_comment_versions import CollectCommentVersions
from .collect_user_posts import CollectUserPosts


class CollectProfileBundle:
    """Entrega posts antes dos comentários, permitindo persistência por unidade."""

    def __init__(
        self, profile_api: IProfileApiPort, comment_api: ICommentApiPort, clock: IClockPort
    ) -> None:
        """Inicializa o caso de uso.

        Args:
            profile_api: porta de leitura do perfil na API móvel.
            comment_api: porta de leitura dos comentários na API móvel.
            clock: relógio do carimbo de coleta.
        """
        self._posts = CollectUserPosts(profile_api, clock)
        self._comments = CollectCommentVersions(comment_api, clock)

    def execute(
        self, command: ProfileCollectionCommand
    ) -> Iterator[CollectionResult[Post | Comment]]:
        """Continua outras postagens quando uma coleta de comentários falha.

        A entrada chega validada no comando: durante a coleta, falhas viram
        resultados com ``error`` em vez de exceções.
        """
        result = self._collect_posts(command)
        yield result
        versions = command.comment_versions
        if versions is None:
            return
        for post in result.items:
            try:
                comments = CommentCollectionCommand(
                    reference_post(post),
                    limit=command.comments_limit,
                    versions=versions,
                )
            except KwaiCollectorError as exc:
                yield CollectionResult("comments", (), error=exc)
                continue
            yield from self._comments.execute(comments)

    def _collect_posts(self, command: ProfileCollectionCommand) -> CollectionResult[Post]:
        try:
            posts = self._posts.execute(command)
        except KwaiCollectorError as exc:
            return CollectionResult.failed("posts", exc, Post)
        return CollectionResult("posts", tuple(posts))

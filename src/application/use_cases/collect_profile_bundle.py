"""Coleta sequencial de posts e versões de comentários, isolada por postagem."""

from __future__ import annotations

from collections.abc import Iterator

from ...domain.entities.comment import Comment
from ...domain.entities.post import Post
from ...domain.exceptions.domain_exceptions import KwaiCollectorError
from ...domain.services.post_urls import reference_post
from ..dtos.collection_result import CollectionResult
from ..dtos.commands import CommentCollectionCommand, ProfileCollectionCommand
from ..ports.use_case_ports import (
    ICollectCommentVersionsPort,
    ICollectProfileBundlePort,
    ICollectUserPostsPort,
)


class CollectProfileBundle(ICollectProfileBundlePort):
    """Entrega posts antes dos comentários, permitindo persistência por unidade."""

    def __init__(self, posts: ICollectUserPostsPort, comments: ICollectCommentVersionsPort) -> None:
        """Inicializa o caso de uso com as coletas que ele encadeia.

        Args:
            posts: coleta das postagens do perfil.
            comments: coleta das versões de comentários de cada postagem.
        """
        self._posts = posts
        self._comments = comments

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
                    reference_post(post), command.comments_limit, versions
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

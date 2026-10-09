"""Coleta sequencial de posts e versões de comentários, isolada por postagem."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import cast

from ..domain.exceptions import InvalidInputError, KwaiCollectorError
from ..domain.identity import normalize_handle
from .collect_comments import CollectCommentVersions
from .collect_user_posts import CollectUserPosts
from .collection_result import CollectionResult
from .exceptions import CollectionInterruptedError
from .models import Post


@dataclass(frozen=True)
class ProfileCollectionOptions:
    """Limites independentes e versões solicitadas pelo chamador."""

    limit: int | None = None
    comments_limit: int | None = None
    with_comments: bool = False
    with_replies: bool = False
    sort_by: str | None = None


class CollectProfileBundle:
    """Entrega posts antes dos comentários, permitindo persistência por unidade."""

    def __init__(self, posts: CollectUserPosts, comments: CollectCommentVersions) -> None:
        self._posts = posts
        self._comments = comments

    def execute(
        self,
        user: str,
        options: ProfileCollectionOptions,
    ) -> Iterator[CollectionResult]:
        """Continua outras postagens quando uma coleta de comentários falha."""
        normalize_handle(user)
        for limit in (options.limit, options.comments_limit):
            if limit is not None and limit < 1:
                raise InvalidInputError("limites devem ser positivos")
        result = self._collect_posts(user, options)
        yield result
        if not (options.with_comments or options.with_replies):
            return
        # A origem explícita é CollectUserPosts, cujo parcial contém Post.
        for post in cast(tuple[Post, ...], result.items):
            try:
                yield from self._comments.execute(
                    post.url,
                    limit=options.comments_limit,
                    with_comments=options.with_comments,
                    with_replies=options.with_replies,
                )
            except KwaiCollectorError as exc:
                yield CollectionResult("comments", (), "roots", post.url, exc)

    def _collect_posts(self, user: str, options: ProfileCollectionOptions) -> CollectionResult:
        try:
            posts = self._posts.execute(user, limit=options.limit, sort_by=options.sort_by)
            return CollectionResult("posts", tuple(posts), "posts")
        except KwaiCollectorError as exc:
            partial = exc.partial if isinstance(exc, CollectionInterruptedError) else ()
            return CollectionResult("posts", partial, "posts", error=exc)

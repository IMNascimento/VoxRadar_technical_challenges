"""Ordenação estável de posts por uma contagem existente, sem alterar métricas."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from ..entities.post import Engagement, Post
from ..enums.post_sort_by import PostSortBy
from ..exceptions.domain_exceptions import InvalidInputError

_METRIC_READERS: dict[PostSortBy, Callable[[Engagement], int | None]] = {
    PostSortBy.LIKES: lambda engagement: engagement.curtidas,
    PostSortBy.COMMENTS: lambda engagement: engagement.comentarios,
    PostSortBy.SHARES: lambda engagement: engagement.compartilhamentos,
    PostSortBy.VIEWS: lambda engagement: engagement.visualizacoes,
}


def validate_sort_by(value: str | None) -> PostSortBy | None:
    """Valida antes de iniciar coleta, inclusive para chamadores Python."""
    if value is None:
        return None
    try:
        return PostSortBy(value)
    except ValueError as exc:
        raise InvalidInputError(
            f"sort_by inválido: {value!r}; use likes, comments, shares ou views"
        ) from exc


def order_posts(posts: Sequence[Post], sort_by: PostSortBy | None) -> list[Post]:
    """Ordena os posts recebidos; desconhecidos no fim, empates na ordem original."""
    if sort_by is None:
        return list(posts)
    read_metric = _METRIC_READERS[sort_by]

    def key(post: Post) -> tuple[bool, int]:
        value = read_metric(post.engajamento)
        return value is not None, value if value is not None else 0

    return sorted(posts, key=key, reverse=True)

"""Ordenação estável de posts por uma contagem existente, sem alterar métricas."""

from __future__ import annotations

from collections.abc import Sequence

from ..entities.post import Post
from ..enums.post_sort_by import PostSortBy
from ..exceptions.domain_exceptions import InvalidInputError


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

    def key(post: Post) -> tuple[bool, int]:
        value = post.engajamento.count(sort_by)
        return value is not None, value if value is not None else 0

    return sorted(posts, key=key, reverse=True)

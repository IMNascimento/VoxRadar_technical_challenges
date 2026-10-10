"""Ordenação de postagens por uma métrica de engajamento, sem alterar as métricas.

A ordem é decrescente e estável: empates mantêm a ordem original e contagens
desconhecidas (``None``) ficam no fim.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..entities.post import Post
from ..enums.post_sort_by import PostSortBy
from ..exceptions.domain_exceptions import InvalidInputError


def validate_sort_by(value: str | None) -> PostSortBy | None:
    """Converte o nome da métrica em :class:`PostSortBy`, validando antes da coleta.

    Args:
        value: nome da métrica (``likes``, ``comments``, ``shares`` ou ``views``).

    Returns:
        A métrica correspondente, ou ``None`` quando nenhuma ordenação foi pedida.

    Raises:
        InvalidInputError: se o nome não for uma métrica aceita.
    """
    if value is None:
        return None
    try:
        return PostSortBy(value)
    except ValueError as exc:
        raise InvalidInputError(
            f"sort_by inválido: {value!r}; use likes, comments, shares ou views"
        ) from exc


def order_posts(posts: Sequence[Post], sort_by: PostSortBy | None) -> list[Post]:
    """Ordena as postagens do maior para o menor valor da métrica escolhida.

    Contagens desconhecidas ficam no fim e empates mantêm a ordem original; sem
    ``sort_by``, devolve uma cópia na ordem recebida.
    """
    if sort_by is None:
        return list(posts)

    def key(post: Post) -> tuple[bool, int]:
        value = post.engajamento.count(sort_by)
        return value is not None, value if value is not None else 0

    return sorted(posts, key=key, reverse=True)

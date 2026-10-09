"""Comandos de entrada dos casos de uso, validados antes de qualquer requisição.

O entrypoint monta o comando a partir dos argumentos crus com ``create``; o
caso de uso recebe os valores já validados (``Handle``, ``PostReference``,
``PostSortBy``) e não repete a validação. As regras de identidade e de
ordenação vêm dos serviços de domínio; aqui só se convertem os argumentos.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ...domain.enums.post_sort_by import PostSortBy
from ...domain.exceptions.domain_exceptions import InvalidInputError
from ...domain.services.post_ordering import validate_sort_by
from ...domain.services.post_urls import parse_post_reference
from ...domain.value_objects.identifiers import Handle
from ...domain.value_objects.post_reference import PostReference

_POSTS_LIMIT_NAME = "limite de postagens"
_COMMENTS_LIMIT_NAME = "limite de comentários"


def _ensure_positive_limit(limit: int | None, *, name: str) -> None:
    """Rejeita um limite informado que não seja positivo; ``None`` é sem teto."""
    if limit is not None and limit < 1:
        raise InvalidInputError(f"{name} deve ser positivo: {limit}")


@dataclass(frozen=True)
class SearchCommand:
    """Busca por palavras-chave, com limite total e ordenação opcional."""

    keywords: tuple[str, ...]
    limit: int = 20
    sort_by: PostSortBy | None = None

    def __post_init__(self) -> None:
        if not self.keywords:
            raise InvalidInputError("informe ao menos uma palavra-chave")
        _ensure_positive_limit(self.limit, name=_POSTS_LIMIT_NAME)

    @classmethod
    def create(
        cls, keywords: Sequence[str], *, limit: int = 20, sort_by: str | None = None
    ) -> SearchCommand:
        """Valida os argumentos crus da busca.

        Raises:
            InvalidInputError: sem palavra-chave, ``limit`` não positivo ou ``sort_by`` inválido.
        """
        return cls(tuple(keywords), limit, validate_sort_by(sort_by))


@dataclass(frozen=True)
class CommentCollectionCommand:
    """Versões de comentários pedidas para uma postagem."""

    post: PostReference
    limit: int | None = None
    with_comments: bool = True
    with_replies: bool = False

    def __post_init__(self) -> None:
        _ensure_positive_limit(self.limit, name=_COMMENTS_LIMIT_NAME)

    @classmethod
    def create(
        cls,
        post_url: str,
        *,
        limit: int | None = None,
        with_comments: bool = True,
        with_replies: bool = False,
    ) -> CommentCollectionCommand:
        """Valida a URL da postagem e o limite de raízes.

        Raises:
            InvalidInputError: se a URL ou o ``limit`` forem inválidos.
        """
        return cls(parse_post_reference(post_url), limit, with_comments, with_replies)


@dataclass(frozen=True)
class ProfileCollectionCommand:
    """Postagens de um perfil e, opcionalmente, versões de comentários por postagem."""

    handle: Handle
    limit: int | None = None
    comments_limit: int | None = None
    with_comments: bool = False
    with_replies: bool = False
    sort_by: PostSortBy | None = None

    def __post_init__(self) -> None:
        _ensure_positive_limit(self.limit, name=_POSTS_LIMIT_NAME)
        _ensure_positive_limit(self.comments_limit, name=_COMMENTS_LIMIT_NAME)

    @classmethod
    def create(
        cls,
        user: str,
        *,
        limit: int | None = None,
        comments_limit: int | None = None,
        with_comments: bool = False,
        with_replies: bool = False,
        sort_by: str | None = None,
    ) -> ProfileCollectionCommand:
        """Normaliza a conta e valida limites e ordenação.

        Raises:
            InvalidInputError: se a conta, algum limite ou ``sort_by`` forem inválidos.
        """
        return cls(
            Handle.parse(user),
            limit,
            comments_limit,
            with_comments,
            with_replies,
            validate_sort_by(sort_by),
        )

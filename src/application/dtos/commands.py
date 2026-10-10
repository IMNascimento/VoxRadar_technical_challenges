"""Comandos de entrada dos casos de uso, validados antes de qualquer requisição.

O entrypoint monta o comando a partir dos argumentos crus com ``create``; o
caso de uso recebe os valores já validados (``Handle``, ``PostReference``,
``PostSortBy``, ``CommentVersions``) e não repete a validação. As regras de
identidade e de ordenação vêm do domínio; aqui só se convertem os argumentos.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

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


class CommentVersions(StrEnum):
    """Versões de comentários entregues por postagem; sempre ao menos uma."""

    ROOTS = "roots"
    REPLIES = "replies"
    ALL = "all"

    @property
    def has_roots(self) -> bool:
        """Indica se a versão só de raízes é entregue."""
        return self is not CommentVersions.REPLIES

    @property
    def has_replies(self) -> bool:
        """Indica se a versão com raízes e respostas é entregue."""
        return self is not CommentVersions.ROOTS

    @classmethod
    def from_flags(cls, *, roots: bool, replies: bool) -> CommentVersions | None:
        """Converte as duas opções da CLI; ``None`` quando nenhuma versão foi pedida."""
        if roots and replies:
            return cls.ALL
        if roots:
            return cls.ROOTS
        if replies:
            return cls.REPLIES
        return None


@dataclass(frozen=True)
class SearchCommand:
    """Comando de busca por palavras-chave, já validado.

    Attributes:
        keywords: palavras-chave, consultadas em ordem até atingir ``limit``.
        limit: teto de postagens únicas no resultado final.
        sort_by: métrica da ordenação decrescente, aplicada após ``limit``;
            ``None`` mantém a ordem de coleta.
    """

    keywords: tuple[str, ...]
    limit: int = 20
    sort_by: PostSortBy | None = None

    def __post_init__(self) -> None:
        if not self.keywords:
            raise InvalidInputError("informe ao menos uma palavra-chave")
        for keyword in self.keywords:
            if not keyword.strip():
                raise InvalidInputError(f"palavra-chave em branco: {keyword!r}")
        _ensure_positive_limit(self.limit, name=_POSTS_LIMIT_NAME)

    @classmethod
    def create(
        cls, keywords: Sequence[str], *, limit: int = 20, sort_by: str | None = None
    ) -> SearchCommand:
        """Valida os argumentos crus da busca.

        Raises:
            InvalidInputError: sem palavra-chave, palavra-chave em branco,
                ``limit`` não positivo ou ``sort_by`` inválido.
        """
        return cls(tuple(keywords), limit, validate_sort_by(sort_by))


@dataclass(frozen=True)
class CommentCollectionCommand:
    """Comando de coleta das versões de comentários de uma postagem, já validado.

    Attributes:
        post: postagem alvo, referenciada pelo id extraído da URL.
        limit: teto de raízes cruas (antes da deduplicação); respostas não contam.
            ``None`` coleta todas.
        versions: versões de comentários a entregar.
    """

    post: PostReference
    limit: int | None = None
    versions: CommentVersions = CommentVersions.ROOTS

    def __post_init__(self) -> None:
        _ensure_positive_limit(self.limit, name=_COMMENTS_LIMIT_NAME)

    @classmethod
    def create(
        cls,
        post_url: str,
        *,
        limit: int | None = None,
        versions: CommentVersions = CommentVersions.ROOTS,
    ) -> CommentCollectionCommand:
        """Valida a URL da postagem e o limite de raízes.

        Raises:
            InvalidInputError: se a URL ou o ``limit`` forem inválidos.
        """
        return cls(parse_post_reference(post_url), limit, versions)


@dataclass(frozen=True)
class ProfileCollectionCommand:
    """Comando de coleta das postagens de um perfil e, opcionalmente, dos comentários.

    Attributes:
        handle: conta normalizada, sem ``@``.
        limit: teto de postagens únicas; ``None`` coleta todas.
        comments_limit: teto de raízes cruas por postagem; ``None`` coleta todas.
        comment_versions: versões de comentários por postagem; ``None`` dispensa
            a coleta de comentários.
        sort_by: métrica da ordenação decrescente, aplicada após ``limit``.
    """

    handle: Handle
    limit: int | None = None
    comments_limit: int | None = None
    comment_versions: CommentVersions | None = None
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
        comment_versions: CommentVersions | None = None,
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
            comment_versions,
            validate_sort_by(sort_by),
        )

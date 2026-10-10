"""Resultado de uma unidade de coleta, separado de sua apresentação em JSON."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Literal, TypeVar

from ...domain.entities.comment import Comment
from ...domain.entities.post import Post
from ...domain.exceptions.domain_exceptions import KwaiCollectorError
from ...domain.value_objects.post_reference import PostReference
from ..exceptions import partial_items

CollectionKind = Literal["posts", "comments", "comments-replies"]
CollectionStage = Literal["posts", "roots", "replies"]

_STAGE_BY_KIND: dict[CollectionKind, CollectionStage] = {
    "posts": "posts",
    "comments": "roots",
    "comments-replies": "replies",
}

ItemT = TypeVar("ItemT", bound=Post | Comment, covariant=True)
_FailedT = TypeVar("_FailedT", bound=Post | Comment)


@dataclass(frozen=True)
class CollectionResult(Generic[ItemT]):
    """Resultado de uma etapa de coleta: os itens obtidos e a falha, se houver.

    Vazio sem ``error`` é sucesso válido; com ``error``, ``items`` é o parcial.

    Attributes:
        kind: tipo de coleta: postagens, raízes de comentários ou raízes com respostas.
        items: itens coletados (o parcial, quando houver ``error``).
        post: postagem de origem; obrigatória em coletas de comentários, exceto
            quando a falha foi justamente identificá-la.
        error: falha da etapa, quando houver.
    """

    kind: CollectionKind
    items: tuple[ItemT, ...]
    post: PostReference | None = None
    error: KwaiCollectorError | None = None

    def __post_init__(self) -> None:
        if self.kind != "posts" and self.post is None and self.error is None:
            raise ValueError(f"resultado {self.kind!r} exige post")

    @property
    def stage(self) -> CollectionStage:
        """Etapa executada, derivada do tipo de coleta."""
        return _STAGE_BY_KIND[self.kind]

    @classmethod
    def failed(
        cls,
        kind: CollectionKind,
        exc: KwaiCollectorError,
        item_type: type[_FailedT],
        *,
        post: PostReference | None = None,
    ) -> CollectionResult[_FailedT]:
        """Monta o resultado de uma etapa que falhou, com o parcial que a falha carregar."""
        return CollectionResult(kind, partial_items(exc, item_type), post=post, error=exc)

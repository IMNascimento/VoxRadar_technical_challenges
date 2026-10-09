"""Identificadores, chaves de deduplicação e a regra de primeira ocorrência."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from typing import Generic, TypeVar

from ..entities.comment import Comment
from ..entities.post import Post

ItemT = TypeVar("ItemT")


def post_dedup_key(post_id: str | None, url: str) -> str:
    """Chave de deduplicação de postagem: ``id`` quando houver, senão ``url``."""
    return post_id or url


def comment_dedup_key(comment_id: str | None, author_id: str | None, text: str) -> str:
    """Chave de deduplicação de comentário: ``id`` ou ``autor``/``texto`` sem ambiguidade.

    Sem ``id``, o autor é prefixado pelo próprio comprimento antes do texto, o
    que torna a chave injetiva: pares ambíguos (ex.: autor ``a:b`` com texto
    ``c`` vs. autor ``a`` com texto ``b:c``) não colidem.
    """
    author = "" if author_id is None else author_id
    return comment_id or f"{len(author)}:{author}{text}"


class UniqueItems(Generic[ItemT]):
    """Mantém só a primeira ocorrência de cada item pela chave de identidade.

    Uma instância guarda as chaves já vistas; compartilhá-la entre lotes
    deduplica entre eles (ex.: raízes e respostas de uma mesma expansão).
    """

    def __init__(self, key: Callable[[ItemT], str]) -> None:
        """Inicializa sem chaves vistas.

        Args:
            key: chave de deduplicação do item.
        """
        self._key = key
        self._seen: set[str] = set()

    def add(self, item: ItemT) -> bool:
        """Registra o item; ``False`` se a chave dele já tinha sido vista."""
        key = self._key(item)
        if key in self._seen:
            return False
        self._seen.add(key)
        return True

    def filter(self, items: Iterable[ItemT]) -> Iterator[ItemT]:
        """Itens inéditos, na ordem de entrada, registrando cada um ao passar."""
        return (item for item in items if self.add(item))


def unique_posts() -> UniqueItems[Post]:
    """Deduplicação de postagens por :func:`post_dedup_key`."""
    return UniqueItems(lambda post: post_dedup_key(post.id, post.url))


def unique_comments() -> UniqueItems[Comment]:
    """Deduplicação de comentários por :func:`comment_dedup_key`."""
    return UniqueItems(
        lambda comment: comment_dedup_key(comment.id, comment.autor.id, comment.texto)
    )

"""Deduplicação pela regra de primeira ocorrência, com a identidade de cada entidade."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from typing import Generic, TypeVar

from ..entities.comment import Comment
from ..entities.post import Post

ItemT = TypeVar("ItemT")


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
        """Filtra os itens inéditos, na ordem de entrada, registrando cada um ao passar."""
        return (item for item in items if self.add(item))


def unique_posts() -> UniqueItems[Post]:
    """Cria o deduplicador de postagens por :attr:`Post.dedup_key`."""
    return UniqueItems(lambda post: post.dedup_key)


def unique_comments() -> UniqueItems[Comment]:
    """Cria o deduplicador de comentários por :attr:`Comment.dedup_key`."""
    return UniqueItems(lambda comment: comment.dedup_key)

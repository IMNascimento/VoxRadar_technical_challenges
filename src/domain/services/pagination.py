"""Paginação por ``pcursor``: regra de continuação, fim e laço de cursor."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Protocol, TypeVar

from ..exceptions.domain_exceptions import RepeatedCursorError
from ..value_objects.cursor import Cursor


class Page(Protocol):
    """Página de uma lista paginada: só o que a regra de paginação precisa conhecer."""

    @property
    def next_cursor(self) -> Cursor:
        """Cursor da próxima página."""
        ...


PageT = TypeVar("PageT", bound=Page)


def iter_pages(
    fetch: Callable[[Cursor], PageT],
    *,
    is_empty: Callable[[PageT], bool],
    source: str,
) -> Iterator[PageT]:
    """Percorre as páginas, de forma preguiçosa, até o fim da paginação.

    Cada página é buscada só quando o consumidor a pede; parar de consumir
    (ex.: limite atingido) não gera requisição extra. A paginação acaba numa
    página vazia ou num cursor de fim (:meth:`Cursor.is_end`).

    Args:
        fetch: busca a página que começa no cursor dado (vazio na primeira).
        is_empty: indica se a página não trouxe itens.
        source: nome da lista paginada, usado só na mensagem de erro.

    Yields:
        As páginas, na ordem em que a API as entrega.

    Raises:
        RepeatedCursorError: se a API devolver um cursor já visto (laço).
    """
    seen_cursors: set[str] = set()
    cursor = Cursor("")
    while True:
        page = fetch(cursor)
        yield page
        next_cursor = page.next_cursor
        if is_empty(page) or next_cursor.is_end():
            return
        if next_cursor.value in seen_cursors:
            raise RepeatedCursorError(f"cursor de {source} repetido: {next_cursor.value!r}")
        seen_cursors.add(next_cursor.value)
        cursor = next_cursor

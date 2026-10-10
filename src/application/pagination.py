"""Coordena a busca preguiçosa de páginas usando a política pura do domínio."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Protocol, TypeVar

from ..domain.services.pagination import get_continuation_cursor
from ..domain.value_objects.cursor import Cursor


class Page(Protocol):
    """Página de uma lista paginada, vista apenas pelo cursor de continuação que carrega."""

    @property
    def next_cursor(self) -> Cursor:
        """Retorna o cursor da próxima página."""
        ...


PageT = TypeVar("PageT", bound=Page)


def iter_pages(
    fetch: Callable[[Cursor], PageT],
    *,
    is_empty: Callable[[PageT], bool],
    source: str,
) -> Iterator[PageT]:
    """Busca páginas sob demanda e entrega cada uma antes de checar a continuação.

    Parar de consumir, inclusive ao atingir um limite, não busca página extra.

    Args:
        fetch: busca a página para o cursor informado (vazio na primeira).
        is_empty: indica se a página mapeada não trouxe itens.
        source: nome da lista paginada, usado só na mensagem de erro.

    Yields:
        As páginas, na ordem em que a porta as entrega.

    Raises:
        RepeatedCursorError: se a continuação já tiver sido aceita nesta coleta.
    """
    seen_cursors: set[str] = set()
    cursor = Cursor("")
    while True:
        page = fetch(cursor)
        yield page
        next_cursor = get_continuation_cursor(
            page.next_cursor, is_empty=is_empty(page), seen_cursors=seen_cursors, source=source
        )
        if next_cursor is None:
            return
        seen_cursors.add(next_cursor.value)
        cursor = next_cursor

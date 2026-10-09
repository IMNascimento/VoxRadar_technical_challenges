"""Paginação por ``pcursor`` compartilhada pelos casos de uso (sem rede)."""

from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass

import pytest

from src.domain.exceptions.domain_exceptions import RepeatedCursorError
from src.domain.services.pagination import iter_pages
from src.domain.value_objects.cursor import Cursor


@dataclass(frozen=True)
class _Page:
    items: list[str]
    next_cursor: Cursor


class _Server:
    """Serve páginas pré-definidas e registra o cursor de cada chamada."""

    def __init__(self, pages: list[_Page]) -> None:
        self._pages = pages
        self.cursors: list[str] = []

    def fetch(self, cursor: Cursor) -> _Page:
        self.cursors.append(cursor.value)
        return self._pages[len(self.cursors) - 1]


def _is_empty(page: _Page) -> bool:
    return not page.items


def test_pagina_ate_o_cursor_de_fim() -> None:
    server = _Server([_Page(["a"], Cursor("P2")), _Page(["b"], Cursor(""))])

    pages = list(iter_pages(server.fetch, is_empty=_is_empty, source="teste"))

    assert [page.items for page in pages] == [["a"], ["b"]]
    assert server.cursors == ["", "P2"]


def test_para_na_pagina_vazia_mesmo_com_cursor_de_continuacao() -> None:
    server = _Server([_Page([], Cursor("P2"))])

    pages = list(iter_pages(server.fetch, is_empty=_is_empty, source="teste"))

    assert len(pages) == 1
    assert server.cursors == [""]


def test_cursor_repetido_levanta_erro_com_a_origem_e_o_valor() -> None:
    server = _Server(
        [_Page(["a"], Cursor("A")), _Page(["b"], Cursor("B")), _Page(["c"], Cursor("A"))]
    )

    with pytest.raises(RepeatedCursorError, match=r"cursor de lista X repetido: 'A'"):
        list(iter_pages(server.fetch, is_empty=_is_empty, source="lista X"))

    assert server.cursors == ["", "A", "B"]


def test_e_preguicoso_a_proxima_pagina_so_e_buscada_quando_pedida() -> None:
    server = _Server([_Page(["a"], Cursor("P2")), _Page(["b"], Cursor(""))])

    pages = iter_pages(server.fetch, is_empty=_is_empty, source="teste")
    assert isinstance(pages, Generator)
    first = next(pages)
    pages.close()

    assert first.items == ["a"]
    assert server.cursors == [""]

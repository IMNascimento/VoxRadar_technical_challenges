"""Regra pura de paginação: decide se a lista continua, termina ou entrou em laço.

Não busca páginas nem guarda estado; quem itera é
:func:`src.application.pagination.iter_pages`.
"""

from __future__ import annotations

from collections.abc import Collection

from ..exceptions.domain_exceptions import RepeatedCursorError
from ..value_objects.cursor import Cursor


def get_continuation_cursor(
    cursor: Cursor,
    *,
    is_empty: bool,
    seen_cursors: Collection[str],
    source: str,
) -> Cursor | None:
    """Decide a continuação sem buscar páginas nem alterar os cursores vistos.

    Args:
        cursor: continuação recebida na página atual.
        is_empty: indica se a página mapeada não trouxe itens.
        seen_cursors: continuações já aceitas nesta coleta.
        source: nome da lista paginada, usado só na mensagem de erro.

    Returns:
        A continuação válida, ou ``None`` quando a página encerra a coleta.

    Raises:
        RepeatedCursorError: se a API devolver um cursor já visto (laço).
    """
    if is_empty or cursor.is_end():
        return None
    if cursor.value in seen_cursors:
        raise RepeatedCursorError(f"cursor de {source} repetido: {cursor.value!r}")
    return cursor

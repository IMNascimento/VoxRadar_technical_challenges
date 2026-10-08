"""Exceções da camada de aplicação: paginação e coleta interrompida."""

from __future__ import annotations

from collections.abc import Sequence
from typing import NoReturn

from pydantic import BaseModel

from ..domain.exceptions import KwaiCollectorError


class RepeatedCursorError(KwaiCollectorError):
    """A API devolveu um ``pcursor`` já visto: a paginação entrou em laço."""


class CollectionInterruptedError(KwaiCollectorError):
    """A coleta falhou no meio, mas já havia itens coletados.

    A causa original fica em ``__cause__``; o que foi coletado até a falha vai em
    ``partial``, para o chamador decidir se aproveita.

    Attributes:
        partial: itens coletados antes da falha, na ordem de coleta.
    """

    def __init__(self, cause: KwaiCollectorError, *, partial: Sequence[BaseModel]) -> None:
        """Inicializa a interrupção com a causa e o que já foi coletado.

        Args:
            cause: falha que interrompeu a coleta.
            partial: itens coletados até a falha (não vazio).
        """
        super().__init__(f"coleta interrompida após {len(partial)} item(ns): {cause}")
        self.partial: tuple[BaseModel, ...] = tuple(partial)


def reraise_with_partial(cause: KwaiCollectorError, partial: Sequence[BaseModel]) -> NoReturn:
    """Relevanta ``cause``, preservando o que já foi coletado.

    Sem itens coletados não há o que preservar: a própria ``cause`` sobe.

    Args:
        cause: falha que interrompeu a coleta.
        partial: itens coletados até a falha.

    Raises:
        CollectionInterruptedError: se ``partial`` não estiver vazio.
        KwaiCollectorError: a própria ``cause``, se ``partial`` estiver vazio.
    """
    if not partial:
        raise cause
    raise CollectionInterruptedError(cause, partial=partial) from cause

"""Exceções da camada de aplicação: coleta interrompida com resultado parcial."""

from __future__ import annotations

from collections.abc import Sequence
from typing import NoReturn, TypeVar

from ..domain.exceptions.domain_exceptions import KwaiCollectorError

ItemT = TypeVar("ItemT")


class CollectionInterruptedError(KwaiCollectorError):
    """A coleta falhou no meio, mas já havia itens coletados.

    A causa original fica em ``__cause__``; o que foi coletado até a falha vai em
    ``partial``, para o chamador decidir se aproveita.

    Attributes:
        partial: itens coletados antes da falha, na ordem de coleta.
    """

    def __init__(self, cause: KwaiCollectorError, *, partial: Sequence[object]) -> None:
        """Inicializa a interrupção com a causa e o que já foi coletado.

        Args:
            cause: falha que interrompeu a coleta.
            partial: itens coletados até a falha (não vazio).
        """
        super().__init__(f"coleta interrompida após {len(partial)} item(ns): {cause}")
        self.partial: tuple[object, ...] = tuple(partial)


def reraise_with_partial(cause: KwaiCollectorError, partial: Sequence[object]) -> NoReturn:
    """Relança ``cause``, preservando o que já foi coletado.

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


def partial_items(exc: KwaiCollectorError, item_type: type[ItemT]) -> tuple[ItemT, ...]:
    """Itens do tipo pedido que a falha carrega: o parcial de uma interrupção ou nenhum.

    Args:
        exc: falha de coleta capturada.
        item_type: entidade dos itens que a coleta produz.

    Returns:
        O ``partial`` de :class:`CollectionInterruptedError`; vazio para as demais falhas.
    """
    if not isinstance(exc, CollectionInterruptedError):
        return ()
    return tuple(item for item in exc.partial if isinstance(item, item_type))

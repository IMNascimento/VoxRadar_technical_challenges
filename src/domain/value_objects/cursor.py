"""Cursor de paginação de uma lista paginada."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Cursor:
    """Cursor de paginação; vazio significa que não há próxima página.

    Os sentinelas de fim de cada API são traduzidos para o cursor vazio pelo
    adapter, então o domínio não conhece o protocolo de nenhuma origem.
    """

    value: str

    def is_end(self) -> bool:
        """Indica se o cursor marca o fim da paginação."""
        return not self.value

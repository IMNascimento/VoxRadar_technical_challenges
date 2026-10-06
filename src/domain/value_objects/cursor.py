"""Cursor de paginação (``pcursor``) da API do Kwai."""

from __future__ import annotations

from dataclasses import dataclass

# Valores de ``pcursor`` que significam fim da paginação.
END_CURSORS: frozenset[str] = frozenset({"", "no_more", "nomore", "-1", "0"})


@dataclass(frozen=True)
class Cursor:
    """Cursor de paginação da API do Kwai."""

    value: str

    def is_end(self) -> bool:
        """Indica se o cursor marca o fim da paginação."""
        return self.value in END_CURSORS

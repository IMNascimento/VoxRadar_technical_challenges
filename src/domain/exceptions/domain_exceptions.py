"""Exceções de domínio do coletor."""

from __future__ import annotations


class KwaiCollectorError(Exception):
    """Erro base do coletor."""


class InvalidInputError(KwaiCollectorError):
    """Entrada inválida fornecida pelo usuário (ex.: URL fora do padrão)."""


class InvalidValueError(KwaiCollectorError):
    """Valor vindo da API ou do próprio coletor viola a invariante de um value object."""


class RepeatedCursorError(KwaiCollectorError):
    """A API devolveu um ``pcursor`` já visto: a paginação entrou em laço."""

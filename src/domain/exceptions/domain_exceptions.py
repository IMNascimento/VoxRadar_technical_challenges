"""Exceções de domínio do coletor: a raiz comum e os erros de entrada, valor e paginação."""

from __future__ import annotations


class KwaiCollectorError(Exception):
    """Raiz das falhas esperadas da coleta; o que não herda dela é erro inesperado."""


class InvalidInputError(KwaiCollectorError):
    """Entrada inválida fornecida pelo usuário (ex.: URL fora do padrão)."""


class InvalidValueError(KwaiCollectorError):
    """Valor vindo da API ou do próprio coletor viola a invariante de um value object."""


class RepeatedCursorError(KwaiCollectorError):
    """A API devolveu um ``pcursor`` já visto: a paginação entrou em laço."""

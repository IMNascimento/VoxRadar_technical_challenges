"""Métricas de engajamento aceitas na ordenação de postagens."""

from __future__ import annotations

from enum import StrEnum


class PostSortBy(StrEnum):
    """Métrica de engajamento que ordena as postagens, sempre do maior para o menor."""

    LIKES = "likes"
    COMMENTS = "comments"
    SHARES = "shares"
    VIEWS = "views"

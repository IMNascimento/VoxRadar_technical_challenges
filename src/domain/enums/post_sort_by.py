"""Contagem usada na ordenação de postagens."""

from __future__ import annotations

from enum import StrEnum


class PostSortBy(StrEnum):
    """Contagem individual usada na ordenação decrescente."""

    LIKES = "likes"
    COMMENTS = "comments"
    SHARES = "shares"
    VIEWS = "views"

"""Valida que as amostras versionadas aderem às entidades do contrato."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from src.domain.entities.comment import Comment, CommentAuthor
from src.domain.entities.post import Engagement, Post, PostAuthor

SAMPLES = Path(__file__).parent.parent.parent / "samples"


def _post(item: dict[str, Any]) -> object:
    return Post(
        **{
            **item,
            "autor": PostAuthor(**item["autor"]),
            "engajamento": Engagement(**item["engajamento"]),
        }
    )


def _comment(item: dict[str, Any]) -> object:
    return Comment(**{**item, "autor": CommentAuthor(**item["autor"])})


CASES: list[tuple[str, Callable[[dict[str, Any]], object]]] = [
    ("busca.json", _post),
    ("usuario.json", _post),
    ("comentarios.json", _comment),
]


@pytest.mark.parametrize(("name", "build"), CASES)
def test_amostra_aderente_ao_contrato(name: str, build: Callable[[dict[str, Any]], object]) -> None:
    """Campo ausente ou desconhecido faz o construtor falhar com ``TypeError``."""
    data = json.loads((SAMPLES / name).read_text(encoding="utf-8"))
    assert isinstance(data, list)
    assert data
    for item in data:
        build(item)

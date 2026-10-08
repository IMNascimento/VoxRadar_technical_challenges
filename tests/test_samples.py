"""Valida que as amostras versionadas aderem aos modelos de contrato."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import BaseModel

from src.application.models import Comment, Post

SAMPLES = Path(__file__).parent.parent / "samples"

CASES: list[tuple[str, type[BaseModel]]] = [
    ("busca.json", Post),
    ("usuario.json", Post),
    ("comentarios.json", Comment),
]


@pytest.mark.parametrize(("name", "model"), CASES)
def test_amostra_aderente_ao_contrato(name: str, model: type[BaseModel]) -> None:
    data = json.loads((SAMPLES / name).read_text(encoding="utf-8"))
    assert isinstance(data, list)
    assert data
    for item in data:
        model.model_validate(item)

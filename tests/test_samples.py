"""Valida que as amostras versionadas aderem aos modelos de contrato."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.application.models import Comentario, Postagem

SAMPLES = Path(__file__).parent.parent / "samples"

CASES = [
    ("busca.json", Postagem),
    ("usuario.json", Postagem),
    ("comentarios.json", Comentario),
]


@pytest.mark.parametrize(("name", "model"), CASES)
def test_amostra_aderente_ao_contrato(name: str, model: type[Any]) -> None:
    data = json.loads((SAMPLES / name).read_text(encoding="utf-8"))
    assert isinstance(data, list)
    assert data
    for item in data:
        model.model_validate(item)

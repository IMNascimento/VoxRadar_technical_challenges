from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import BaseModel

from kwai_collector.models.comentario import Comentario
from kwai_collector.models.postagem import Postagem

SAMPLES_DIRECTORY = Path(__file__).resolve().parents[1] / "samples"


@pytest.mark.parametrize(
    ("filename", "model", "required_fields"),
    [
        (
            "exemplo_busca.json",
            Postagem,
            {"url", "engajamento", "coletado_em"},
        ),
        (
            "exemplo_perfil.json",
            Postagem,
            {"url", "engajamento", "coletado_em"},
        ),
        (
            "exemplo_comentarios.json",
            Comentario,
            {"postagem_url", "texto", "coletado_em"},
        ),
    ],
)
def test_official_samples_follow_output_contract(
    filename: str,
    model: type[BaseModel],
    required_fields: set[str],
) -> None:
    records = json.loads((SAMPLES_DIRECTORY / filename).read_text(encoding="utf-8"))

    assert isinstance(records, list), "Official samples must match the CLI list output."
    assert records, "Official samples must contain at least one record."
    for record in records:
        assert isinstance(record, dict)
        assert required_fields.issubset(record)
        model.model_validate(record)

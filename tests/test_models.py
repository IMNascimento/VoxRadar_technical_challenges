"""Testes dos modelos de contrato."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.application.models import Comentario, Engajamento, Postagem


def test_postagem_campos_obrigatorios() -> None:
    post = Postagem(
        url="https://www.kwai.com/@perfil/video/1",
        engajamento=Engajamento(curtidas=10),
        coletado_em="2026-07-27T14:30:00Z",
    )
    assert post.url.endswith("/video/1")
    assert post.autor.usuario is None
    assert post.engajamento.curtidas == 10


def test_postagem_url_obrigatoria() -> None:
    with pytest.raises(ValidationError):
        Postagem(engajamento=Engajamento(), coletado_em="2026-07-27T14:30:00Z")  # type: ignore[call-arg]


def test_postagem_rejeita_campo_extra() -> None:
    with pytest.raises(ValidationError):
        Postagem(
            url="https://www.kwai.com/@p/video/1",
            engajamento=Engajamento(),
            coletado_em="2026-07-27T14:30:00Z",
            desconhecido="x",  # type: ignore[call-arg]
        )


def test_comentario_texto_obrigatorio() -> None:
    with pytest.raises(ValidationError):
        Comentario(  # type: ignore[call-arg]
            postagem_url="https://www.kwai.com/@p/video/1",
            coletado_em="2026-07-27T14:30:00Z",
        )

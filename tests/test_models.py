"""Testes dos modelos de contrato."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.application.models import Comment, Engagement, Post


def test_postagem_campos_obrigatorios() -> None:
    post = Post(
        url="https://www.kwai.com/@perfil/video/1",
        engajamento=Engagement(curtidas=10),
        coletado_em="2026-07-27T14:30:00Z",
    )
    assert post.url.endswith("/video/1")
    assert post.autor.usuario is None
    assert post.engajamento.curtidas == 10


def test_postagem_url_obrigatoria() -> None:
    with pytest.raises(ValidationError):
        Post(engajamento=Engagement(), coletado_em="2026-07-27T14:30:00Z")  # type: ignore[call-arg]


def test_postagem_rejeita_campo_extra() -> None:
    with pytest.raises(ValidationError):
        Post(
            url="https://www.kwai.com/@p/video/1",
            engajamento=Engagement(),
            coletado_em="2026-07-27T14:30:00Z",
            desconhecido="x",  # type: ignore[call-arg]
        )


def test_comentario_texto_obrigatorio() -> None:
    with pytest.raises(ValidationError):
        Comment(  # type: ignore[call-arg]
            postagem_url="https://www.kwai.com/@p/video/1",
            coletado_em="2026-07-27T14:30:00Z",
        )

"""Testes das entidades do contrato."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from src.domain.entities.comment import Comment, ExpandedComment
from src.domain.entities.post import Engagement, Post


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
    with pytest.raises(TypeError):
        Post(engajamento=Engagement(), coletado_em="2026-07-27T14:30:00Z")  # type: ignore[call-arg]


def test_postagem_rejeita_campo_extra() -> None:
    with pytest.raises(TypeError):
        Post(
            url="https://www.kwai.com/@p/video/1",
            engajamento=Engagement(),
            coletado_em="2026-07-27T14:30:00Z",
            desconhecido="x",  # type: ignore[call-arg]
        )


def test_postagem_e_imutavel() -> None:
    post = Post(url="u", engajamento=Engagement(), coletado_em="2026-07-27T14:30:00Z")
    with pytest.raises(FrozenInstanceError):
        post.url = "outra"  # type: ignore[misc]


def test_comentario_texto_obrigatorio() -> None:
    with pytest.raises(TypeError):
        Comment(  # type: ignore[call-arg]
            postagem_url="https://www.kwai.com/@p/video/1",
            coletado_em="2026-07-27T14:30:00Z",
        )


def test_comentario_expandido_preserva_o_contrato_oficial() -> None:
    comment = Comment(id="r1", postagem_url="u", texto="t", coletado_em="2026-07-27T14:30:00Z")

    expanded = ExpandedComment.from_comment(comment, respostas_total=2)

    assert expanded.id == "r1"
    assert expanded.texto == "t"
    assert expanded.parent_id is None
    assert expanded.respostas_total == 2

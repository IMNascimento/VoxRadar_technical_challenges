"""Testes de parsing (feed -> Postagem, comentários -> Comentario)."""

from __future__ import annotations

from typing import Any

import pytest

from src.infrastructure.exceptions import UnexpectedResponseError
from src.infrastructure.mapping import (
    build_post_url,
    parse_comment,
    parse_feed,
    parse_sub_comment,
)
from src.shared.utils.timestamps import iso_from_timestamp_ms

FIXED = "2026-09-08T00:00:00Z"


def test_iso_from_timestamp_ms() -> None:
    assert iso_from_timestamp_ms(1727902079867) == "2024-10-02T20:47:59Z"
    assert iso_from_timestamp_ms(0) is None
    assert iso_from_timestamp_ms(None) is None
    assert iso_from_timestamp_ms("not-a-number") is None


def test_build_post_url() -> None:
    assert build_post_url("perfil", "123") == "https://www.kwai.com/@perfil/video/123"
    assert build_post_url(None, "123") is None
    assert build_post_url("perfil", None) is None


def test_parse_feed_da_busca(search_response: dict[str, Any]) -> None:
    feed = search_response["feeds"][0]
    post = parse_feed(feed, collected_at=FIXED)

    assert post.url == f"https://www.kwai.com/@{feed['kwai_id']}/video/{feed['photo_id_str']}"
    assert post.id == feed["photo_id_str"]
    assert post.autor.usuario == f"@{feed['kwai_id']}"
    assert post.autor.url_perfil == f"https://www.kwai.com/@{feed['kwai_id']}"
    assert post.engajamento.curtidas == feed["like_count"]
    assert post.engajamento.visualizacoes == feed["view_count"]
    assert post.coletado_em == FIXED
    # valor exato conhecido (timestamp 1720226579842 ms da fixture)
    assert post.data_publicacao == "2024-07-06T00:42:59Z"


def test_parse_feed_usa_photo_id_str_preservando_precisao(profile_feeds: dict[str, Any]) -> None:
    feed = profile_feeds["feeds"][0]
    post = parse_feed(feed, collected_at=FIXED)
    # photo_id como número perde precisão; o parser deve usar a versão string.
    assert post.id == feed["photo_id_str"]
    assert post.id in post.url


def test_parse_feed_campos_ausentes() -> None:
    post = parse_feed({"photo_id_str": "9", "kwai_id": "x"}, collected_at=FIXED)
    assert post.engajamento.curtidas is None
    assert post.texto is None
    assert post.data_publicacao is None


def test_parse_feed_desescapa_html() -> None:
    post = parse_feed(
        {"photo_id_str": "9", "kwai_id": "x", "caption": "V&iacute;deo &amp; cia"},
        collected_at=FIXED,
    )
    assert post.texto == "Vídeo & cia"


def test_parse_feed_nao_inventa_carimbo_sem_collected_at() -> None:
    """O parser não gera carimbo próprio: o carimbo vem da camada de orquestração."""
    with pytest.raises(TypeError):
        parse_feed({"photo_id_str": "9", "kwai_id": "x"})  # type: ignore[call-arg]


def test_parse_feed_sem_photo_id_nao_inventa_url() -> None:
    """Feed sem ``photo_id`` levanta erro em vez de fabricar uma URL inválida."""
    with pytest.raises(UnexpectedResponseError):
        parse_feed({"kwai_id": "x"}, collected_at=FIXED)


def test_parse_comment_mapeia_campos_com_carimbo_passado() -> None:
    comment = parse_comment(
        {
            "comment_id": "c_1",
            "content": "oi",
            "author_name": "Autor",
            "author_id": "a1",
            "liked_count": "5",
            "timestamp": 1720226579842,
        },
        postagem_url="https://www.kwai.com/@p/video/1",
        collected_at=FIXED,
    )
    assert comment.id == "c_1"
    assert comment.texto == "oi"
    assert comment.autor.usuario == "Autor"
    assert comment.autor.id == "a1"
    assert comment.curtidas == 5  # "5" (str) coerido
    assert comment.data == "2024-07-06T00:42:59Z"
    assert comment.coletado_em == FIXED  # o carimbo é exatamente o passado


def test_parse_sub_comment_mapeia_vinculo() -> None:
    sub = parse_sub_comment(
        {
            "comment_id": "s_1",
            "content": "resposta",
            "author_name": "Quem responde",
            "author_id": "a2",
            "liked_count": 7,
            "reply_to": 150001404765512,
            "replyToUserName": "Fulano",
            "timestamp": 1720226579842,
        },
        postagem_url="https://www.kwai.com/@p/video/1",
        collected_at=FIXED,
    )
    assert sub.comentario.id == "s_1"
    assert sub.comentario.texto == "resposta"
    assert sub.comentario.curtidas == 7
    assert sub.reply_to_id == "150001404765512"
    assert sub.reply_to_usuario == "Fulano"


def test_parse_sub_comment_reply_to_zero_vira_none() -> None:
    sub = parse_sub_comment(
        {"comment_id": "s_2", "content": "oi", "reply_to": 0, "author_id": "a3"},
        postagem_url="https://www.kwai.com/@p/video/1",
        collected_at=FIXED,
    )
    assert sub.reply_to_id is None
    assert sub.reply_to_usuario is None

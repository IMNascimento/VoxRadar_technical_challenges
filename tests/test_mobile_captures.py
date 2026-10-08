"""Regressões offline sobre recortes sanitizados de respostas reais do app."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import respx

from src.application.collect_comments import CollectComments
from src.config import Settings
from src.domain.value_objects.cursor import Cursor
from src.domain.value_objects.identifiers import CommentId, PhotoId, UserId
from src.domain.value_objects.iso_timestamp import IsoTimestamp
from src.infrastructure.mobile_client import (
    COMMENT_HOST,
    COMMENT_PATH,
    PROFILE_FEED_PATH,
    SUBLIST_PATH,
    MobileApiAdapter,
)

FIXTURES = Path(__file__).parent / "fixtures"
URL = "https://www.kwai.com/@ajudantedoreid/video/5210251923800764971"
STAMP = IsoTimestamp("2026-10-07T00:00:00Z")


def _load(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@respx.mock
def test_captured_comment_pages_preserve_fields_and_send_next_cursor(settings: Settings) -> None:
    pages = _load("mobile_comments.json")
    route = respx.post(COMMENT_HOST + COMMENT_PATH).mock(
        side_effect=[httpx.Response(200, json=page) for page in pages]
    )
    client = MobileApiAdapter(settings)
    try:
        comments = CollectComments(client).execute(URL, limit=4)
    finally:
        client.close()
    assert [comment.id for comment in comments] == [
        "155133451079517322",
        "155135477229291002",
        "219432891068711995",
        "218628635892908506",
    ]
    assert (
        comments[0].texto
        == "esse carro não serve para você rapaz, compra outro e me dá esse kkkkk chama"
    )
    assert comments[0].autor.id == "150001404765512"
    assert comments[0].autor.usuario == "Gonzaga da fz 25"
    assert comments[0].curtidas == 427
    assert comments[0].data == "2024-11-11T21:49:22Z"
    assert comments[2].curtidas == 0
    assert len(route.calls) == 2
    assert b"pcursor=m_0" in route.calls[1].request.content


@respx.mock
def test_captured_replies_preserve_target_user_and_continuation(settings: Settings) -> None:
    respx.post(COMMENT_HOST + SUBLIST_PATH).mock(
        return_value=httpx.Response(200, json=_load("mobile_replies.json"))
    )
    client = MobileApiAdapter(settings)
    try:
        page = client.fetch_sub_page(
            PhotoId("5210251923800764971"),
            root_comment_id=CommentId("155133451079517322"),
            cursor=Cursor(""),
            count=100,
            postagem_url=URL,
            collected_at=STAMP,
        )
    finally:
        client.close()
    first = page.comments[0]
    assert first.comentario.id == "155178446230652028"
    assert first.comentario.texto == "io[heart_eyes][joy][kiss][big_eyes]"
    assert first.comentario.autor.id == "150001455582225"
    assert first.comentario.curtidas == 1
    assert first.comentario.data == "2024-11-12T09:29:38Z"
    assert first.reply_to_id == "150001404765512"
    assert first.reply_to_usuario == "Gonzaga da fz 25"
    assert page.next_cursor.value == "t_155269891455190337_1731488887238"
    assert len(page.comments) == 3


@respx.mock
def test_captured_profile_preserves_caption_metrics_and_cursor(settings: Settings) -> None:
    respx.post(COMMENT_HOST + PROFILE_FEED_PATH).mock(
        return_value=httpx.Response(200, json=_load("mobile_profile.json"))
    )
    client = MobileApiAdapter(settings)
    try:
        page = client.fetch_profile_page(
            UserId("150001752740839"),
            cursor=Cursor(""),
            count=30,
            collected_at=STAMP,
        )
    finally:
        client.close()
    post = page.posts[0]
    assert post.id == "5239243853418407006"
    assert post.url == "https://www.kwai.com/@puratabela/video/5239243853418407006"
    assert post.autor.id == "150001752740839"
    assert post.texto == "#aimodel #aestheticgirl #feminineenergy #reelsviral #ExplorePage"
    assert post.engajamento.model_dump() == {
        "curtidas": 4,
        "comentarios": 0,
        "compartilhamentos": 0,
        "visualizacoes": 239,
    }
    assert page.next_cursor.value == "1.789088531315E12"

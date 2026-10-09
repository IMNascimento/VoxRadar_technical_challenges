"""Regressões offline sobre recortes sanitizados de respostas reais do app."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import httpx
import respx

from src.application.dtos.commands import CommentCollectionCommand
from src.application.ports.clock_port import IClockPort
from src.application.use_cases.collect_comment_versions import CollectCommentVersions
from src.config.settings import Settings
from src.domain.value_objects.cursor import Cursor
from src.domain.value_objects.identifiers import CommentId, PhotoId, UserId
from src.domain.value_objects.iso_timestamp import IsoTimestamp
from src.domain.value_objects.post_reference import PostReference
from src.infrastructure.kwai.mobile.adapter import (
    COMMENT_PATH,
    PROFILE_FEED_PATH,
    SUBLIST_PATH,
    MobileApiAdapter,
)
from src.infrastructure.kwai.mobile.client import COMMENT_HOST, MobileApiClient

FIXTURES = Path(__file__).parent.parent / "fixtures"
URL = "https://www.kwai.com/@ajudantedoreid/video/5210251923800764971"
STAMP = IsoTimestamp("2026-10-07T00:00:00Z")


class _FixedClock(IClockPort):
    def now(self) -> IsoTimestamp:
        return STAMP


def _load(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@respx.mock
def test_captured_comment_pages_preserve_fields_and_send_next_cursor(settings: Settings) -> None:
    pages = _load("mobile_comments.json")
    route = respx.post(COMMENT_HOST + COMMENT_PATH).mock(
        side_effect=[httpx.Response(200, json=page) for page in pages]
    )
    client = MobileApiClient(settings)
    adapter = MobileApiAdapter(client)
    try:
        command = CommentCollectionCommand.create(URL, limit=4)
        (result,) = CollectCommentVersions(adapter, _FixedClock()).execute(command)
        comments = result.items
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
    client = MobileApiClient(settings)
    adapter = MobileApiAdapter(client)
    try:
        page = adapter.fetch_sub_page(
            PostReference(PhotoId("5210251923800764971"), URL),
            root_comment_id=CommentId("155133451079517322"),
            cursor=Cursor(""),
            collected_at=STAMP,
        )
    finally:
        client.close()
    first = page.comments[0]
    assert first.comment.id == "155178446230652028"
    assert first.comment.texto == "io[heart_eyes][joy][kiss][big_eyes]"
    assert first.comment.autor.id == "150001455582225"
    assert first.comment.curtidas == 1
    assert first.comment.data == "2024-11-12T09:29:38Z"
    assert first.reply_to_id == "150001404765512"
    assert first.reply_to_usuario == "Gonzaga da fz 25"
    assert page.next_cursor.value == "t_155269891455190337_1731488887238"
    assert len(page.comments) == 3


@respx.mock
def test_captured_profile_preserves_caption_metrics_and_cursor(settings: Settings) -> None:
    respx.post(COMMENT_HOST + PROFILE_FEED_PATH).mock(
        return_value=httpx.Response(200, json=_load("mobile_profile.json"))
    )
    client = MobileApiClient(settings)
    adapter = MobileApiAdapter(client)
    try:
        page = adapter.fetch_profile_page(
            UserId("150001752740839"),
            cursor=Cursor(""),
            collected_at=STAMP,
        )
    finally:
        client.close()
    post = page.posts[0]
    assert post.id == "5239243853418407006"
    assert post.url == "https://www.kwai.com/@puratabela/video/5239243853418407006"
    assert post.autor.id == "150001752740839"
    assert post.texto == "#aimodel #aestheticgirl #feminineenergy #reelsviral #ExplorePage"
    assert asdict(post.engajamento) == {
        "curtidas": 4,
        "comentarios": 0,
        "compartilhamentos": 0,
        "visualizacoes": 239,
    }
    assert page.next_cursor.value == "1.789088531315E12"

"""Respostas malformadas: erros tratados e preservação das páginas anteriores."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest
import respx

from src.application.collect_comments import CollectComments
from src.application.collect_user_posts import CollectUserPosts
from src.application.exceptions import CollectionInterruptedError
from src.application.search_posts import SearchPosts
from src.config import Settings
from src.domain.value_objects.cursor import Cursor
from src.domain.value_objects.identifiers import CommentId, Handle, PhotoId, UserId
from src.domain.value_objects.iso_timestamp import IsoTimestamp
from src.infrastructure.exceptions import UnexpectedResponseError
from src.infrastructure.mapping import parse_feeds
from src.infrastructure.mobile_client import (
    COMMENT_HOST,
    COMMENT_PATH,
    PROFILE_FEED_PATH,
    SUBLIST_PATH,
    USER_INFO_PATH,
    MobileApiAdapter,
)
from src.infrastructure.web_client import SEARCH_PATH, KwaiWebAdapter

URL = "https://www.kwai.com/@perfil/video/123"
STAMP = IsoTimestamp("2026-10-07T00:00:00Z")


def _fetch_roots(client: MobileApiAdapter) -> object:
    return client.fetch_page(
        PhotoId("123"), cursor=Cursor(""), count=5, postagem_url=URL, collected_at=STAMP
    )


def _fetch_replies(client: MobileApiAdapter) -> object:
    return client.fetch_sub_page(
        PhotoId("123"),
        root_comment_id=CommentId("r1"),
        cursor=Cursor(""),
        count=5,
        postagem_url=URL,
        collected_at=STAMP,
    )


def _fetch_profile(client: MobileApiAdapter) -> object:
    return client.fetch_profile_page(UserId("1"), cursor=Cursor(""), count=5, collected_at=STAMP)


PAGE_ROUTES: list[tuple[str, str, Callable[[MobileApiAdapter], object]]] = [
    (COMMENT_PATH, "rootComments", _fetch_roots),
    (SUBLIST_PATH, "subComments", _fetch_replies),
    (PROFILE_FEED_PATH, "feeds", _fetch_profile),
]


@pytest.mark.parametrize(("path", "field", "fetch"), PAGE_ROUTES)
@pytest.mark.parametrize("invalid", [{}, "wrong", 0, False])
@respx.mock
def test_page_rejects_non_list_collection(
    settings: Settings,
    path: str,
    field: str,
    fetch: Callable[[MobileApiAdapter], object],
    invalid: Any,
) -> None:
    route = respx.post(COMMENT_HOST + path).mock(
        return_value=httpx.Response(200, json={"result": 1, "pcursor": "no_more", field: invalid})
    )
    client = MobileApiAdapter(settings)
    try:
        with pytest.raises(UnexpectedResponseError) as exc:
            fetch(client)
    finally:
        client.close()
    assert field in str(exc.value)
    assert len(route.calls) == 1


@pytest.mark.parametrize(("path", "field", "fetch"), PAGE_ROUTES[:2])
@pytest.mark.parametrize("invalid", [None, "wrong", []])
@respx.mock
def test_comment_page_reports_invalid_item_without_technical_exception(
    settings: Settings,
    path: str,
    field: str,
    fetch: Callable[[MobileApiAdapter], object],
    invalid: Any,
) -> None:
    respx.post(COMMENT_HOST + path).mock(
        return_value=httpx.Response(200, json={"result": 1, "pcursor": "no_more", field: [invalid]})
    )
    client = MobileApiAdapter(settings)
    try:
        with pytest.raises(UnexpectedResponseError) as exc:
            fetch(client)
    finally:
        client.close()
    assert f"{field}[0]" in str(exc.value)
    assert path in str(exc.value)


@pytest.mark.parametrize(("path", "field", "fetch"), PAGE_ROUTES)
@pytest.mark.parametrize("invalid", [{}, [], True])
@respx.mock
def test_page_rejects_non_scalar_cursor(
    settings: Settings,
    path: str,
    field: str,
    fetch: Callable[[MobileApiAdapter], object],
    invalid: Any,
) -> None:
    respx.post(COMMENT_HOST + path).mock(
        return_value=httpx.Response(200, json={"result": 1, "pcursor": invalid, field: []})
    )
    client = MobileApiAdapter(settings)
    try:
        with pytest.raises(UnexpectedResponseError, match="pcursor"):
            fetch(client)
    finally:
        client.close()


@pytest.mark.parametrize("invalid", [{}, "wrong", False])
def test_feed_collection_rejects_invalid_container(invalid: Any) -> None:
    with pytest.raises(UnexpectedResponseError, match="feeds"):
        parse_feeds(invalid, collected_at=STAMP.value)


@respx.mock
def test_malformed_second_comment_page_preserves_first_page(settings: Settings) -> None:
    route = respx.post(COMMENT_HOST + COMMENT_PATH).mock(
        side_effect=[
            httpx.Response(
                200,
                json={
                    "result": 1,
                    "pcursor": "NEXT",
                    "rootComments": [{"comment_id": "r1", "content": "valid"}],
                },
            ),
            httpx.Response(200, json={"result": 1, "pcursor": "no_more", "rootComments": [None]}),
        ]
    )
    client = MobileApiAdapter(settings)
    try:
        with pytest.raises(CollectionInterruptedError) as exc:
            CollectComments(client).execute(URL)
    finally:
        client.close()
    assert isinstance(exc.value.__cause__, UnexpectedResponseError)
    assert [item.model_dump()["id"] for item in exc.value.partial] == ["r1"]
    assert len(route.calls) == 2


@respx.mock
def test_malformed_reply_page_preserves_roots(settings: Settings) -> None:
    respx.post(COMMENT_HOST + COMMENT_PATH).mock(
        return_value=httpx.Response(
            200,
            json={
                "result": 1,
                "pcursor": "no_more",
                "rootComments": [
                    {"comment_id": "r1", "content": "root", "sub_comment_count": 1},
                    {"comment_id": "r2", "content": "other root"},
                ],
            },
        )
    )
    respx.post(COMMENT_HOST + SUBLIST_PATH).mock(
        return_value=httpx.Response(
            200,
            json={
                "result": 1,
                "pcursor": "no_more",
                "subComments": ["wrong"],
            },
        )
    )
    client = MobileApiAdapter(settings)
    try:
        with pytest.raises(CollectionInterruptedError) as exc:
            CollectComments(client).execute(URL, with_replies=True)
    finally:
        client.close()
    assert isinstance(exc.value.__cause__, UnexpectedResponseError)
    assert [item.model_dump()["id"] for item in exc.value.partial] == ["r1", "r2"]


@respx.mock
def test_user_resolution_rejects_malformed_list(settings: Settings) -> None:
    respx.post(COMMENT_HOST + USER_INFO_PATH).mock(
        return_value=httpx.Response(200, json={"result": 1, "users": {"user_id": 1}})
    )
    client = MobileApiAdapter(settings)
    try:
        with pytest.raises(UnexpectedResponseError, match="users"):
            client.resolve_user(Handle("perfil"))
    finally:
        client.close()


@respx.mock
def test_malformed_second_profile_page_preserves_first_page(settings: Settings) -> None:
    respx.post(COMMENT_HOST + USER_INFO_PATH).mock(
        return_value=httpx.Response(200, json={"result": 1, "users": [{"user_id": 1}]})
    )
    respx.post(COMMENT_HOST + PROFILE_FEED_PATH).mock(
        side_effect=[
            httpx.Response(
                200,
                json={
                    "result": 1,
                    "pcursor": "NEXT",
                    "feeds": [{"photo_id_str": "1", "kwai_id": "perfil"}],
                },
            ),
            httpx.Response(200, json={"result": 1, "pcursor": "no_more", "feeds": "wrong"}),
        ]
    )
    client = MobileApiAdapter(settings)
    try:
        with pytest.raises(CollectionInterruptedError) as exc:
            CollectUserPosts(client).execute("@perfil")
    finally:
        client.close()
    assert isinstance(exc.value.__cause__, UnexpectedResponseError)
    assert [item.model_dump()["id"] for item in exc.value.partial] == ["1"]


@respx.mock
def test_malformed_second_search_batch_preserves_first_keyword(settings: Settings) -> None:
    respx.post("https://www.kwai.com" + SEARCH_PATH).mock(
        side_effect=[
            httpx.Response(
                200, json={"result": 1, "feeds": [{"photo_id_str": "1", "kwai_id": "perfil"}]}
            ),
            httpx.Response(200, json={"result": 1, "feeds": {}}),
        ]
    )
    client = KwaiWebAdapter(settings)
    try:
        with pytest.raises(CollectionInterruptedError) as exc:
            SearchPosts(client).execute(["first", "second"])
    finally:
        client.close()
    assert isinstance(exc.value.__cause__, UnexpectedResponseError)
    assert [item.model_dump()["id"] for item in exc.value.partial] == ["1"]

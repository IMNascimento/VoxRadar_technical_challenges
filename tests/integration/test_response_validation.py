"""Respostas malformadas: erros tratados e preservação das páginas anteriores."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest
import respx

from src.application.dtos.commands import (
    CommentCollectionCommand,
    ProfileCollectionCommand,
    SearchCommand,
)
from src.application.exceptions import CollectionInterruptedError
from src.application.ports.clock_port import IClockPort
from src.application.use_cases.collect_comment_versions import CollectCommentVersions
from src.application.use_cases.collect_user_posts import CollectUserPosts
from src.application.use_cases.search_posts import SearchPosts
from src.config.settings import Settings
from src.domain.value_objects.cursor import Cursor
from src.domain.value_objects.identifiers import CommentId, Handle, PhotoId, UserId
from src.domain.value_objects.iso_timestamp import IsoTimestamp
from src.domain.value_objects.post_reference import PostReference
from src.infrastructure.kwai.exceptions import UnexpectedResponseError
from src.infrastructure.kwai.mapping import parse_feeds
from src.infrastructure.kwai.mobile.adapter import (
    COMMENT_PATH,
    PROFILE_FEED_PATH,
    SUBLIST_PATH,
    USER_INFO_PATH,
    MobileApiAdapter,
)
from src.infrastructure.kwai.mobile.client import COMMENT_HOST, MobileApiClient
from src.infrastructure.kwai.web.adapter import SEARCH_PATH, KwaiWebAdapter
from src.infrastructure.kwai.web.client import KwaiWebClient

URL = "https://www.kwai.com/@perfil/video/123"
POST = PostReference(PhotoId("123"), URL)
STAMP = IsoTimestamp("2026-10-07T00:00:00Z")


class _FixedClock(IClockPort):
    def now(self) -> IsoTimestamp:
        return STAMP


_clock = _FixedClock()


def _fetch_roots(adapter: MobileApiAdapter) -> object:
    return adapter.fetch_page(POST, cursor=Cursor(""), collected_at=STAMP)


def _fetch_replies(adapter: MobileApiAdapter) -> object:
    return adapter.fetch_sub_page(
        POST,
        root_comment_id=CommentId("r1"),
        cursor=Cursor(""),
        collected_at=STAMP,
    )


def _fetch_profile(adapter: MobileApiAdapter) -> object:
    return adapter.fetch_profile_page(UserId("1"), cursor=Cursor(""), collected_at=STAMP)


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
    client = MobileApiClient(settings)
    adapter = MobileApiAdapter(client)
    try:
        with pytest.raises(UnexpectedResponseError) as exc:
            fetch(adapter)
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
    client = MobileApiClient(settings)
    adapter = MobileApiAdapter(client)
    try:
        with pytest.raises(UnexpectedResponseError) as exc:
            fetch(adapter)
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
    client = MobileApiClient(settings)
    adapter = MobileApiAdapter(client)
    try:
        with pytest.raises(UnexpectedResponseError, match="pcursor"):
            fetch(adapter)
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
    client = MobileApiClient(settings)
    adapter = MobileApiAdapter(client)
    try:
        (result,) = CollectCommentVersions(adapter, _clock).execute(
            CommentCollectionCommand.create(URL)
        )
    finally:
        client.close()
    assert isinstance(result.error, CollectionInterruptedError)
    assert isinstance(result.error.__cause__, UnexpectedResponseError)
    assert [item.id for item in result.items] == ["r1"]
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
    client = MobileApiClient(settings)
    adapter = MobileApiAdapter(client)
    command = CommentCollectionCommand.create(URL, with_comments=False, with_replies=True)
    try:
        (result,) = CollectCommentVersions(adapter, _clock).execute(command)
    finally:
        client.close()
    assert isinstance(result.error, CollectionInterruptedError)
    assert isinstance(result.error.__cause__, UnexpectedResponseError)
    assert [item.id for item in result.items] == ["r1", "r2"]


@respx.mock
def test_user_resolution_rejects_malformed_list(settings: Settings) -> None:
    respx.post(COMMENT_HOST + USER_INFO_PATH).mock(
        return_value=httpx.Response(200, json={"result": 1, "users": {"user_id": 1}})
    )
    client = MobileApiClient(settings)
    adapter = MobileApiAdapter(client)
    try:
        with pytest.raises(UnexpectedResponseError, match="users"):
            adapter.resolve_user(Handle("perfil"))
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
    client = MobileApiClient(settings)
    adapter = MobileApiAdapter(client)
    try:
        with pytest.raises(CollectionInterruptedError) as exc:
            CollectUserPosts(adapter, _clock).execute(ProfileCollectionCommand.create("@perfil"))
    finally:
        client.close()
    assert isinstance(exc.value.__cause__, UnexpectedResponseError)
    assert [getattr(item, "id", None) for item in exc.value.partial] == ["1"]


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
    client = KwaiWebClient(settings)
    try:
        result = SearchPosts(KwaiWebAdapter(client), _clock).execute(
            SearchCommand.create(["first", "second"])
        )
    finally:
        client.close()
    assert isinstance(result.error, CollectionInterruptedError)
    assert isinstance(result.error.__cause__, UnexpectedResponseError)
    assert [item.id for item in result.items] == ["1"]

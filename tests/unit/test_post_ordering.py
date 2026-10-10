"""Ordenação por contagem individual nos casos de uso, sem rede."""

from __future__ import annotations

from dataclasses import asdict, replace
from unittest.mock import Mock

import pytest

from src.application.dtos.commands import ProfileCollectionCommand, SearchCommand
from src.application.dtos.pages import ProfilePage, SearchPage
from src.application.exceptions import CollectionInterruptedError
from src.application.ports.clock_port import IClockPort
from src.application.ports.profile_api_port import IProfileApiPort
from src.application.ports.search_api_port import ISearchApiPort
from src.application.use_cases.collect_user_posts import CollectUserPosts
from src.application.use_cases.search_posts import SearchPosts
from src.domain.entities.post import Engagement, Post
from src.domain.exceptions.domain_exceptions import InvalidInputError, KwaiCollectorError
from src.domain.value_objects.cursor import Cursor
from src.domain.value_objects.identifiers import UserId
from src.domain.value_objects.iso_timestamp import IsoTimestamp


class _GatewayError(KwaiCollectorError):
    """Falha de porta simulada, sem depender das exceções da infraestrutura."""


class _FixedClock(IClockPort):
    def now(self) -> IsoTimestamp:
        return IsoTimestamp("2026-10-08T00:00:00Z")


_clock = _FixedClock()


def _posts() -> list[Post]:
    return [
        Post(
            id="1",
            url="https://www.kwai.com/@p/video/1",
            coletado_em="2026-10-08T00:00:00Z",
            engajamento=Engagement(
                curtidas=2, comentarios=9, compartilhamentos=3, visualizacoes=10
            ),
        ),
        Post(
            id="2",
            url="https://www.kwai.com/@p/video/2",
            coletado_em="2026-10-08T00:00:00Z",
            engajamento=Engagement(
                curtidas=7, comentarios=1, compartilhamentos=8, visualizacoes=20
            ),
        ),
        Post(
            id="3",
            url="https://www.kwai.com/@p/video/3",
            coletado_em="2026-10-08T00:00:00Z",
            engajamento=Engagement(
                curtidas=4, comentarios=5, compartilhamentos=0, visualizacoes=30
            ),
        ),
    ]


@pytest.mark.parametrize("source", ["profile", "search"])
@pytest.mark.parametrize(
    ("metric", "ids"),
    [
        ("likes", ["2", "3", "1"]),
        ("comments", ["1", "3", "2"]),
        ("shares", ["2", "1", "3"]),
        ("views", ["3", "2", "1"]),
    ],
)
def test_individual_metric_orders_posts_descending(
    source: str, metric: str, ids: list[str]
) -> None:
    posts = _posts()
    before = [asdict(post) for post in posts]
    result: tuple[Post, ...] | list[Post]
    if source == "profile":
        api = Mock(spec=IProfileApiPort)
        api.resolve_user.return_value = UserId("123")
        api.fetch_profile_page.return_value = ProfilePage(posts, Cursor(""))
        command = ProfileCollectionCommand.create("p", sort_by=metric)
        result = CollectUserPosts(api, _clock).execute(command)
    else:
        api = Mock(spec=ISearchApiPort)
        api.search_page.return_value = SearchPage(posts, 0)
        result = SearchPosts(api, _clock).execute(SearchCommand.create(["p"], sort_by=metric)).items
    assert [post.id for post in result] == ids
    assert [asdict(post) for post in posts] == before


def test_limit_selects_posts_before_sorting() -> None:
    api = Mock(spec=ISearchApiPort)
    api.search_page.return_value = SearchPage(_posts(), 0)
    command = SearchCommand.create(["p"], limit=2, sort_by="views")
    result = SearchPosts(api, _clock).execute(command)
    assert [post.id for post in result.items] == ["2", "1"]


def test_unknown_counts_follow_zero_and_ties_preserve_order() -> None:
    posts = [
        replace(post, engajamento=replace(post.engajamento, curtidas=likes))
        for post, likes in zip(_posts(), [None, 0, 0], strict=True)
    ]
    api = Mock(spec=ISearchApiPort)
    api.search_page.return_value = SearchPage(posts, 0)
    result = SearchPosts(api, _clock).execute(SearchCommand.create(["p"], sort_by="likes"))
    assert [post.id for post in result.items] == ["2", "3", "1"]
    assert posts[0].engajamento.curtidas is None


@pytest.mark.parametrize("source", ["profile", "search"])
def test_sorted_partial_preserves_cause(source: str) -> None:
    cause = _GatewayError("second unit failed")
    if source == "profile":
        api = Mock(spec=IProfileApiPort)
        api.resolve_user.return_value = UserId("123")
        api.fetch_profile_page.side_effect = [ProfilePage(_posts(), Cursor("NEXT")), cause]
        collect = CollectUserPosts(api, _clock)
        with pytest.raises(CollectionInterruptedError) as exc:
            collect.execute(ProfileCollectionCommand.create("p", sort_by="likes"))
        error: BaseException = exc.value
        partial = exc.value.partial
    else:
        api = Mock(spec=ISearchApiPort)
        api.search_page.side_effect = [SearchPage(_posts(), 0), cause]
        command = SearchCommand.create(["first", "second"], sort_by="likes")
        result = SearchPosts(api, _clock).execute(command)
        assert isinstance(result.error, CollectionInterruptedError)
        error = result.error
        partial = result.items
    assert [item.id for item in partial if isinstance(item, Post)] == ["2", "3", "1"]
    assert error.__cause__ is cause


@pytest.mark.parametrize("source", ["profile", "search"])
def test_invalid_metric_is_rejected_before_network(source: str) -> None:
    with pytest.raises(InvalidInputError):
        if source == "profile":
            ProfileCollectionCommand.create("p", sort_by="total")
        else:
            SearchCommand.create(["p"], sort_by="total")

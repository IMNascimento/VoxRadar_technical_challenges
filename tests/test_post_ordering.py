"""Ordenação por contagem individual nos casos de uso, sem rede."""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from src.application.collect_user_posts import CollectUserPosts
from src.application.exceptions import CollectionInterruptedError
from src.application.models import Engagement, Post
from src.application.ports import ProfileApiPort, ProfilePage, SearchApiPort
from src.application.search_posts import SearchPosts
from src.domain.exceptions import InvalidInputError
from src.domain.value_objects.cursor import Cursor
from src.domain.value_objects.identifiers import UserId
from src.infrastructure.exceptions import KwaiTransportError


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
    before = [post.model_dump() for post in posts]
    if source == "profile":
        api = Mock(spec=ProfileApiPort)
        api.resolve_user.return_value = UserId("123")
        api.fetch_profile_page.return_value = ProfilePage(posts, Cursor("no_more"))
        result = CollectUserPosts(api).execute("p", sort_by=metric)
    else:
        api = Mock(spec=SearchApiPort)
        api.search_posts.return_value = posts
        result = SearchPosts(api).execute(["p"], sort_by=metric)
    assert [post.id for post in result] == ids
    assert [post.model_dump() for post in posts] == before


def test_limit_selects_posts_before_sorting() -> None:
    api = Mock(spec=SearchApiPort)
    api.search_posts.return_value = _posts()
    result = SearchPosts(api).execute(["p"], limit=2, sort_by="views")
    assert [post.id for post in result] == ["2", "1"]


def test_unknown_counts_follow_zero_and_ties_preserve_order() -> None:
    posts = _posts()
    posts[0].engajamento.curtidas = None
    posts[1].engajamento.curtidas = 0
    posts[2].engajamento.curtidas = 0
    api = Mock(spec=SearchApiPort)
    api.search_posts.return_value = posts
    result = SearchPosts(api).execute(["p"], sort_by="likes")
    assert [post.id for post in result] == ["2", "3", "1"]
    assert posts[0].engajamento.curtidas is None


@pytest.mark.parametrize("source", ["profile", "search"])
def test_sorted_partial_preserves_cause(source: str) -> None:
    cause = KwaiTransportError("second unit failed")
    if source == "profile":
        api = Mock(spec=ProfileApiPort)
        api.resolve_user.return_value = UserId("123")
        api.fetch_profile_page.side_effect = [ProfilePage(_posts(), Cursor("NEXT")), cause]
        collect = CollectUserPosts(api)
        with pytest.raises(CollectionInterruptedError) as exc:
            collect.execute("p", sort_by="likes")
    else:
        api = Mock(spec=SearchApiPort)
        api.search_posts.side_effect = [_posts(), cause]
        with pytest.raises(CollectionInterruptedError) as exc:
            SearchPosts(api).execute(["first", "second"], sort_by="likes")
    assert [item.model_dump()["id"] for item in exc.value.partial] == ["2", "3", "1"]
    assert exc.value.__cause__ is cause


@pytest.mark.parametrize("source", ["profile", "search"])
def test_invalid_metric_is_rejected_before_network(source: str) -> None:
    api = Mock()
    with pytest.raises(InvalidInputError):
        if source == "profile":
            CollectUserPosts(api).execute("p", sort_by="total")
        else:
            SearchPosts(api).execute(["p"], sort_by="total")
    assert not api.mock_calls

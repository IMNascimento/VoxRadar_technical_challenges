"""Novos comandos: HTTP simulado, filesystem real e falhas isoladas."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import Mock
from urllib.parse import parse_qs

import httpx
import pytest
import respx
from typer.testing import CliRunner

from src.application.collect_comments import CollectCommentVersions
from src.application.ports import CommentApiPort, CommentPage
from src.container import Services
from src.domain.exceptions import InvalidInputError
from src.domain.value_objects.cursor import Cursor
from src.entrypoints.cli import app
from src.infrastructure.mobile_client import (
    COMMENT_HOST,
    COMMENT_PATH,
    PROFILE_FEED_PATH,
    SUBLIST_PATH,
    USER_INFO_PATH,
)
from src.infrastructure.web_client import SEARCH_PATH

runner = CliRunner()
ENV = {"KWAI_REQUEST_DELAY": "0", "KWAI_MAX_RETRIES": "0"}
URL = "https://www.kwai.com/@parkour-city/video/123"


def _profile(ids: tuple[str, ...] = ("123", "456")) -> None:
    respx.post(COMMENT_HOST + USER_INFO_PATH).respond(
        200, json={"result": 1, "users": [{"user_id": 123}]}
    )
    respx.post(COMMENT_HOST + PROFILE_FEED_PATH).respond(
        200,
        json={
            "result": 1,
            "pcursor": "no_more",
            "feeds": [{"photo_id_str": pid, "kwai_id": "parkour-city"} for pid in ids],
        },
    )


def _roots(cursor: str = "no_more") -> dict[str, Any]:
    return {
        "result": 1,
        "pcursor": cursor,
        "rootComments": [{"comment_id": "r1", "content": "raiz 🏃", "sub_comment_count": 1}],
    }


def _replies() -> dict[str, Any]:
    return {
        "result": 1,
        "pcursor": "no_more",
        "subComments": [{"comment_id": "s1", "content": "resposta"}],
    }


def _run_dir(base: Path, owner: str = "parkour-city") -> Path:
    runs = list((base / owner).iterdir())
    assert len(runs) == 1
    return runs[0]


def _load(path: Path) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
    return payload


@respx.mock
def test_profile_without_out_creates_default_exports(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _profile()
    result = runner.invoke(app, ["profile", "-u", "@parkour-city", "-l", "1"], env=ENV)
    assert result.exit_code == 0, result.output
    run = _run_dir(tmp_path / "exports")
    assert [item["id"] for item in _load(run / "posts.json")] == ["123"]
    assert not (run / "comments").exists()


@pytest.mark.parametrize(
    ("flags", "simple", "expanded"),
    [
        (["--with-comments"], True, False),
        (["--with-comments-replies"], False, True),
        (["--with-comments", "--with-comments-replies"], True, True),
    ],
)
@respx.mock
def test_profile_exports_requested_versions_once(
    tmp_path: Path,
    flags: list[str],
    simple: bool,
    expanded: bool,
) -> None:
    _profile()
    roots = respx.post(COMMENT_HOST + COMMENT_PATH).respond(200, json=_roots())
    replies = respx.post(COMMENT_HOST + SUBLIST_PATH).respond(200, json=_replies())
    result = runner.invoke(
        app,
        ["profile", "-u", "parkour-city", "-o", str(tmp_path), *flags],
        env=ENV,
    )
    assert result.exit_code == 0, result.output
    run = _run_dir(tmp_path)
    assert len(roots.calls) == 2
    assert len(replies.calls) == (2 if expanded else 0)
    assert (run / "comments").exists() is simple
    assert (run / "comments-replies").exists() is expanded
    if simple:
        assert [item["id"] for item in _load(run / "comments/123.json")] == ["r1"]
        assert "parent_id" not in _load(run / "comments/123.json")[0]
    if expanded:
        data = _load(run / "comments-replies/123.json")
        assert [item["id"] for item in data] == ["r1", "s1"]
        assert data[1]["parent_id"] == "r1"


@respx.mock
def test_profile_comments_limit_does_not_limit_replies(tmp_path: Path) -> None:
    _profile(("123",))
    body = _roots()
    body["rootComments"].append({"comment_id": "r2", "content": "outside limit"})
    respx.post(COMMENT_HOST + COMMENT_PATH).respond(200, json=body)
    respx.post(COMMENT_HOST + SUBLIST_PATH).respond(200, json=_replies())
    result = runner.invoke(
        app,
        [
            "profile",
            "-u",
            "parkour-city",
            "--with-comments-replies",
            "--comments-limit",
            "1",
            "-o",
            str(tmp_path),
        ],
        env=ENV,
    )
    assert result.exit_code == 0, result.output
    assert [item["id"] for item in _load(_run_dir(tmp_path) / "comments-replies/123.json")] == [
        "r1",
        "s1",
    ]


@respx.mock
def test_one_post_failure_does_not_stop_other_posts(tmp_path: Path) -> None:
    _profile()

    def respond(request: httpx.Request) -> httpx.Response:
        photo_id = parse_qs(request.content.decode())["photoId"][0]
        body = {"result": 11, "error_msg": "failed post"} if photo_id == "123" else _roots()
        return httpx.Response(200, json=body)

    respx.post(COMMENT_HOST + COMMENT_PATH).mock(side_effect=respond)
    result = runner.invoke(
        app,
        ["profile", "-u", "parkour-city", "--with-comments", "-o", str(tmp_path)],
        env=ENV,
    )
    assert result.exit_code == 1
    run = _run_dir(tmp_path)
    assert (run / "posts.json").exists()
    assert not (run / "comments/123.json").exists()
    assert _load(run / "comments/456.json")[0]["id"] == "r1"


@respx.mock
def test_root_partial_is_not_published_as_expanded(tmp_path: Path) -> None:
    respx.post(COMMENT_HOST + COMMENT_PATH).mock(
        side_effect=[
            httpx.Response(200, json=_roots("NEXT")),
            httpx.Response(200, json={"result": 1, "rootComments": [None]}),
        ]
    )
    result = runner.invoke(
        app,
        ["comments", "--url", URL, "--with-comments-replies", "-o", str(tmp_path)],
        env=ENV,
    )
    assert result.exit_code == 1
    run = _run_dir(tmp_path)
    assert _load(run / "comments/123.partial.json")[0]["id"] == "r1"
    assert not (run / "comments-replies").exists()


@respx.mock
def test_reply_partial_preserves_complete_simple_version(tmp_path: Path) -> None:
    _profile(("123",))
    respx.post(COMMENT_HOST + COMMENT_PATH).respond(200, json=_roots())
    respx.post(COMMENT_HOST + SUBLIST_PATH).respond(200, json={"result": 11})
    result = runner.invoke(
        app,
        [
            "profile",
            "-u",
            "parkour-city",
            "--with-comments",
            "--with-comments-replies",
            "-o",
            str(tmp_path),
        ],
        env=ENV,
    )
    assert result.exit_code == 1
    run = _run_dir(tmp_path)
    assert _load(run / "comments/123.json")[0]["id"] == "r1"
    assert _load(run / "comments-replies/123.partial.json")[0]["respostas_total"] == 1
    assert not (run / "comments-replies/123.json").exists()


@respx.mock
def test_search_exports_without_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    search_response: dict[str, Any],
) -> None:
    monkeypatch.chdir(tmp_path)
    respx.post("https://www.kwai.com" + SEARCH_PATH).respond(200, json=search_response)
    result = runner.invoke(app, ["search", "-k", "sports", "-k", "parkour", "-l", "1"], env=ENV)
    assert result.exit_code == 0, result.output
    assert len(_load(_run_dir(tmp_path / "exports", "search") / "posts.json")) == 1


@respx.mock
def test_comments_only_exports_roots(tmp_path: Path) -> None:
    respx.post(COMMENT_HOST + COMMENT_PATH).respond(200, json=_roots())
    result = runner.invoke(app, ["comments", "--url", URL, "-o", str(tmp_path)], env=ENV)
    assert result.exit_code == 0, result.output
    assert _load(_run_dir(tmp_path) / "comments/123.json")[0]["texto"] == "raiz 🏃"


@respx.mock
def test_success_is_persisted_before_close_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _profile(("123",))
    original_close = Services.close

    def fail_close(services: Services) -> None:
        original_close(services)
        raise OSError("close failure")

    monkeypatch.setattr(Services, "close", fail_close)
    result = runner.invoke(app, ["profile", "-u", "parkour-city", "-o", str(tmp_path)], env=ENV)
    assert result.exit_code == 1
    assert _load(_run_dir(tmp_path) / "posts.json")[0]["id"] == "123"


@pytest.mark.parametrize("command", [["profile", "-u", "bad/name"], ["comments", "--url", "bad"]])
def test_invalid_target_creates_no_exports(tmp_path: Path, command: list[str]) -> None:
    result = runner.invoke(app, [*command, "-o", str(tmp_path)], env=ENV)
    assert result.exit_code == 2
    assert not list(tmp_path.iterdir())


def test_english_help_explains_directory_output() -> None:
    result = runner.invoke(app, ["profile", "--help"])
    assert result.exit_code == 0
    assert "--with-comments-replies" in result.output
    assert "--comments-limit" in result.output
    assert "exports" in result.output


@pytest.mark.parametrize("failed_name", ["posts.json", "123.json"])
@respx.mock
def test_write_failure_does_not_stop_other_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failed_name: str,
) -> None:
    _profile()
    respx.post(COMMENT_HOST + COMMENT_PATH).respond(200, json=_roots())
    original_replace = Path.replace

    def fail_replace(source: Path, target: str | Path) -> Path:
        if Path(target).name == failed_name:
            raise OSError("simulated disk failure")
        return original_replace(source, target)

    monkeypatch.setattr(Path, "replace", fail_replace)
    result = runner.invoke(
        app,
        ["profile", "-u", "parkour-city", "--with-comments", "-o", str(tmp_path)],
        env=ENV,
    )
    assert result.exit_code == 1
    run = _run_dir(tmp_path)
    assert _load(run / "comments/456.json")[0]["id"] == "r1"
    assert not list(run.rglob("*.tmp"))
    assert not list(run.rglob(failed_name))


@respx.mock
def test_profile_partial_still_enriches_collected_posts(tmp_path: Path) -> None:
    _profile(("123",))
    route = respx.post(COMMENT_HOST + PROFILE_FEED_PATH)
    first = {
        "result": 1,
        "pcursor": "NEXT",
        "feeds": [{"photo_id_str": "123", "kwai_id": "parkour-city"}],
    }
    route.mock(
        side_effect=[httpx.Response(200, json=first), httpx.Response(200, json={"result": 11})]
    )
    respx.post(COMMENT_HOST + COMMENT_PATH).respond(200, json=_roots())
    result = runner.invoke(
        app,
        ["profile", "-u", "parkour-city", "--with-comments", "-o", str(tmp_path)],
        env=ENV,
    )
    assert result.exit_code == 1
    run = _run_dir(tmp_path)
    assert _load(run / "posts.partial.json")[0]["id"] == "123"
    assert _load(run / "comments/123.json")[0]["id"] == "r1"


@respx.mock
def test_repeated_runs_never_overwrite(tmp_path: Path) -> None:
    _profile(("123",))
    args = ["profile", "-u", "parkour-city", "-o", str(tmp_path)]
    assert runner.invoke(app, args, env=ENV).exit_code == 0
    assert runner.invoke(app, args, env=ENV).exit_code == 0
    assert len(list((tmp_path / "parkour-city").glob("*/posts.json"))) == 2


@respx.mock
def test_windows_reserved_profile_name_is_safe(tmp_path: Path) -> None:
    _profile(("123",))
    result = runner.invoke(app, ["profile", "-u", "NUL", "-o", str(tmp_path)], env=ENV)
    assert result.exit_code == 0, result.output
    files = list(tmp_path.rglob("posts.json"))
    assert len(files) == 1
    assert files[0].parent.parent.name.casefold() != "nul"


def test_export_base_file_rejected_before_network(tmp_path: Path) -> None:
    base = tmp_path / "not-a-directory"
    base.write_text("preserve", encoding="utf-8")
    result = runner.invoke(app, ["profile", "-u", "parkour-city", "-o", str(base)], env=ENV)
    assert result.exit_code == 1
    assert base.read_text(encoding="utf-8") == "preserve"


@pytest.mark.parametrize("option", ["--limit", "--comments-limit"])
def test_profile_rejects_nonpositive_limits(tmp_path: Path, option: str) -> None:
    result = runner.invoke(
        app,
        ["profile", "-u", "parkour-city", option, "0", "-o", str(tmp_path)],
        env=ENV,
    )
    assert result.exit_code == 2
    assert not list(tmp_path.iterdir())


def test_comment_versions_rejects_nonpositive_limit_before_http() -> None:
    api = Mock(spec=CommentApiPort)
    api.fetch_page.return_value = CommentPage([], Cursor("no_more"))
    with pytest.raises(InvalidInputError, match="positivo"):
        list(CollectCommentVersions(api).execute(URL, limit=0))
    api.fetch_page.assert_not_called()


@pytest.mark.parametrize("has_previous_items", [False, True])
@respx.mock
def test_search_failure_preserves_only_previous_keywords(
    tmp_path: Path,
    search_response: dict[str, Any],
    has_previous_items: bool,
) -> None:
    responses = [httpx.Response(200, json={"result": 11})]
    if has_previous_items:
        responses.insert(0, httpx.Response(200, json=search_response))
    respx.post("https://www.kwai.com" + SEARCH_PATH).mock(side_effect=responses)
    result = runner.invoke(
        app,
        ["search", "-k", "sports", "-k", "parkour", "-l", "50", "-o", str(tmp_path)],
        env=ENV,
    )
    assert result.exit_code == 1
    run = _run_dir(tmp_path, "search")
    assert not (run / "posts.json").exists()
    assert (run / "posts.partial.json").exists() is has_previous_items


def test_new_cli_invalid_configuration_creates_no_export(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["profile", "-u", "parkour-city", "-o", str(tmp_path)],
        env={"KWAI_HTTP_TIMEOUT": "invalid"},
    )
    assert result.exit_code == 1
    assert not list(tmp_path.iterdir())


@respx.mock
def test_failed_profile_resolution_does_not_publish_posts(tmp_path: Path) -> None:
    respx.post(COMMENT_HOST + USER_INFO_PATH).respond(200, json={"result": 11})
    result = runner.invoke(
        app, ["profile", "-u", "parkour-city", "--with-comments", "-o", str(tmp_path)], env=ENV
    )
    assert result.exit_code == 1
    assert not list(tmp_path.rglob("*.json"))


@respx.mock
def test_reply_failure_keeps_pending_roots_and_continues_next_post(tmp_path: Path) -> None:
    _profile()
    roots = _roots()
    roots["rootComments"].append({"comment_id": "r2", "content": "pending", "sub_comment_count": 1})
    respx.post(COMMENT_HOST + COMMENT_PATH).respond(200, json=roots)

    def respond(request: httpx.Request) -> httpx.Response:
        fields = parse_qs(request.content.decode())
        body = {"result": 11} if fields["photoId"] == ["123"] else _replies()
        return httpx.Response(200, json=body)

    replies = respx.post(COMMENT_HOST + SUBLIST_PATH).mock(side_effect=respond)
    result = runner.invoke(
        app,
        ["profile", "-u", "parkour-city", "--with-comments-replies", "-o", str(tmp_path)],
        env=ENV,
    )
    assert result.exit_code == 1
    run = _run_dir(tmp_path)
    assert [item["id"] for item in _load(run / "comments-replies/123.partial.json")] == ["r1", "r2"]
    assert [item["id"] for item in _load(run / "comments-replies/456.json")] == ["r1", "s1", "r2"]
    calls = [parse_qs(call.request.content.decode()) for call in replies.calls]
    assert [(fields["photoId"][0], fields["rootCommentId"][0]) for fields in calls] == [
        ("123", "r1"),
        ("456", "r1"),
        ("456", "r2"),
    ]


@pytest.mark.parametrize("command", [["profile", "-u", "parkour-city"], ["search", "-k", "sports"]])
@pytest.mark.parametrize(
    ("metric", "field"),
    [
        ("likes", "like_count"),
        ("comments", "comment_count"),
        ("shares", "forward_count"),
        ("views", "view_count"),
    ],
)
@respx.mock
def test_sort_option_exports_descending_posts(
    tmp_path: Path,
    command: list[str],
    metric: str,
    field: str,
) -> None:
    _profile()
    body = {
        "result": 1,
        "pcursor": "no_more",
        "feeds": [
            {"photo_id_str": "123", "kwai_id": "parkour-city", field: 2},
            {"photo_id_str": "456", "kwai_id": "parkour-city", field: 9},
        ],
    }
    respx.post(COMMENT_HOST + PROFILE_FEED_PATH).respond(200, json=body)
    respx.post("https://www.kwai.com" + SEARCH_PATH).respond(200, json=body)
    result = runner.invoke(app, [*command, "--sort-by", metric, "-o", str(tmp_path)], env=ENV)
    assert result.exit_code == 0, result.output
    posts_file = next(tmp_path.rglob("posts.json"))
    assert [item["id"] for item in _load(posts_file)] == ["456", "123"]


def test_invalid_sort_option_creates_no_export(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["profile", "-u", "parkour-city", "--sort-by", "total", "-o", str(tmp_path)],
        env=ENV,
    )
    assert result.exit_code == 2
    assert "Invalid value for '--sort-by'" in result.output
    assert not list(tmp_path.iterdir())

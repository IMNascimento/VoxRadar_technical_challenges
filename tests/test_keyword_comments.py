from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterator, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl

import httpx
import pytest

from kwai_collector import cli
from kwai_collector.config import Settings
from kwai_collector.security.signature_provider import PreparedMobileRequest

KEYWORD = "cafe com leite"
OUTPUT_NAME = "busca_cafe_com_leite"

SESSION_VALUES = (
    "synthetic-token",
    "synthetic-pass-token",
    "synthetic-api-st",
    "synthetic-header",
    "synthetic-device",
    "synthetic-session",
)


class FakeMobileRequestProvider:
    """Provider sintético usado somente nos testes de busca com comentários."""

    def __init__(
        self,
        *,
        query_fields: Mapping[str, str] | None = None,
        body_fields: Mapping[str, str] | None = None,
        header_fields: Mapping[str, str] | None = None,
    ) -> None:
        self.query_fields = dict(query_fields or {})
        self.body_fields = dict(body_fields or {})
        self.header_fields = dict(header_fields or {})

    def prepare(
        self,
        *,
        query: dict[str, str],
        body: dict[str, str],
        headers: dict[str, str],
    ) -> PreparedMobileRequest:
        prepared_query = dict(query)
        prepared_body = dict(body)
        prepared_headers = dict(headers)

        prepared_query.update(self.query_fields)
        prepared_body.update(self.body_fields)
        prepared_headers.update(self.header_fields)

        return PreparedMobileRequest(
            query=prepared_query,
            body=prepared_body,
            headers=prepared_headers,
        )


def _post(
    photo_id: str,
    user_id: str,
    handle: str,
) -> dict[str, Any]:
    return {
        "photo_id_str": photo_id,
        "user_id_str": user_id,
        "kwai_id": handle,
        "user_name": f"Autor {handle}",
        "caption": f"Post sintetico {photo_id}",
        "like_count": 3,
        "comment_count": 65,
        "forward_count": 1,
        "view_count": 100,
    }


def _comment(index: int) -> dict[str, Any]:
    return {
        "commentId": str(index),
        "userName": f"Usuario {index}",
        "kwaiid": f"usuario_{index}",
        "content": f"Comentario {index}",
        "commentLikeCount": index,
    }


def _form(
    request: httpx.Request,
) -> dict[str, str]:
    return dict(
        parse_qsl(
            request.content.decode(),
        )
    )


def _page(
    indices: range,
    cursor: str,
) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "result": 1,
            "rootComments": [_comment(index) for index in indices],
            "pcursor": cursor,
            "subComments": [
                _comment(99999),
            ],
        },
    )


@pytest.fixture
def mobile_keyword_cli(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[
    Callable[
        [Callable[[httpx.Request], httpx.Response]],
        None,
    ]
]:
    """Isola o ambiente e usa um provider sintético nos testes do CLI."""

    for name in list(os.environ):
        if name.startswith("KWAI_"):
            monkeypatch.delenv(name)

    settings = Settings(
        _env_file=None,
        cookie=None,
        mobile_query_fields={
            "did": "synthetic-device",
            "session_id": "synthetic-session",
        },
        mobile_body_fields={
            "token": "synthetic-token",
            "passToken": "synthetic-pass-token",
            "kwaipro.api_st": "synthetic-api-st",
        },
        mobile_header_fields={
            "X-Test-Session": "synthetic-header",
        },
        mobile_auth_endpoint=None,
        mobile_auth_token=None,
        max_tentativas=3,
        backoff_base=0,
        delay=0,
        mobile_page_delay=2,
    )

    monkeypatch.setattr(
        cli,
        "settings",
        settings,
    )

    def fake_auth_provider() -> FakeMobileRequestProvider:
        return FakeMobileRequestProvider(
            query_fields=settings.mobile_query_fields,
            body_fields=settings.mobile_body_fields,
            header_fields=settings.mobile_header_fields,
        )

    monkeypatch.setattr(
        cli,
        "_criar_auth_provider_mobile",
        fake_auth_provider,
    )

    original_client = httpx.Client
    clients: list[httpx.Client] = []

    def install_transport(
        handler: Callable[
            [httpx.Request],
            httpx.Response,
        ],
    ) -> None:
        def mocked_client(
            *args: Any,
            **kwargs: Any,
        ) -> httpx.Client:
            kwargs["transport"] = httpx.MockTransport(
                handler,
            )

            client = original_client(
                *args,
                **kwargs,
            )

            clients.append(
                client,
            )

            return client

        monkeypatch.setattr(
            httpx,
            "Client",
            mocked_client,
        )

    def reject_unexpected_request(
        request: httpx.Request,
    ) -> httpx.Response:
        raise AssertionError(
            f"Unexpected HTTP request: {request.method} {request.url.path}"
        )

    install_transport(
        reject_unexpected_request,
    )

    yield install_transport

    for client in clients:
        client.close()


def _mock_search(
    monkeypatch: pytest.MonkeyPatch,
    posts: list[dict[str, Any]],
    *,
    expected_delay: float = 0,
) -> list[str]:
    keywords: list[str] = []

    def search(
        keyword: str,
        *,
        delay: float,
    ) -> list[dict[str, Any]]:
        keywords.append(
            keyword,
        )

        assert delay == expected_delay

        return posts

    monkeypatch.setattr(
        cli,
        "search_all_posts",
        search,
    )

    return keywords


def _arguments(
    output_dir: Path,
    *,
    limit: str | None = "todos",
) -> list[str]:
    arguments = [
        "buscar",
        KEYWORD,
        "--with-comments",
        "--request-interval",
        "0",
        "--output-dir",
        str(output_dir),
    ]

    if limit is not None:
        arguments.extend(
            [
                "--max-comments",
                limit,
            ]
        )

    return arguments


def _assert_mobile_request(
    request: httpx.Request,
    post: dict[str, Any],
) -> dict[str, str]:
    assert request.method == "POST"
    assert request.url.host == "api2-us.kwaipros.com"
    assert request.url.path == "/rest/o/comment/list/v2"

    assert "cookie" not in request.headers

    form = _form(
        request,
    )

    assert form["photoId"] == post["photo_id_str"]
    assert form["user_id"] == post["user_id_str"]

    assert 1 <= int(form["count"]) <= 20

    assert form["token"] == "synthetic-token"

    assert "client_salt" not in form

    return form


def _read_export(
    output_dir: Path,
    posts: list[dict[str, Any]],
) -> dict[str, Any]:
    listed = json.loads(
        (output_dir / f"{OUTPUT_NAME}.json").read_text(
            encoding="utf-8",
        )
    )

    assert isinstance(
        listed,
        list,
    )

    assert [post["id"] for post in listed] == [post["photo_id_str"] for post in posts]

    assert [post["autor"]["id"] for post in listed] == [
        post["user_id_str"] for post in posts
    ]

    aggregate = json.loads(
        (output_dir / f"{OUTPUT_NAME}_comentarios.json").read_text(
            encoding="utf-8",
        )
    )

    assert aggregate["palavra_chave"] == KEYWORD

    assert datetime.fromisoformat(aggregate["coletado_em"]).tzinfo is not None

    assert aggregate["total_posts_processados"] == len(posts)

    assert aggregate["total_comentarios_coletados"] == sum(
        post["quantidade"] for post in aggregate["posts"]
    )

    for raw, collected in zip(
        posts,
        aggregate["posts"],
        strict=True,
    ):
        assert collected["photo_id"] == raw["photo_id_str"]

        assert collected["url"] == (
            f"https://www.kwai.com/@{raw['kwai_id']}/video/{raw['photo_id_str']}"
        )

        assert collected["caption"] == raw["caption"]

        assert collected["quantidade"] == len(collected["comentarios"])

        individual = json.loads(
            (output_dir / (f"{raw['photo_id_str']}_comentarios.json")).read_text(
                encoding="utf-8",
            )
        )

        assert individual == collected["comentarios"]

        assert all(
            comment["postagem_url"] == collected["url"] for comment in individual
        )

    return aggregate


def test_keyword_comments_collects_all_pages_and_separate_authors(
    monkeypatch: pytest.MonkeyPatch,
    mobile_keyword_cli: Callable,
    tmp_path: Path,
) -> None:
    posts = [
        _post(
            "123",
            "456",
            "autor_um",
        ),
        _post(
            "321",
            "654",
            "autor_dois",
        ),
    ]

    keywords = _mock_search(
        monkeypatch,
        posts,
        expected_delay=0.25,
    )

    requests: list[httpx.Request] = []

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        requests.append(
            request,
        )

        assert len(requests) <= 3

        post = posts[0] if len(requests) <= 2 else posts[1]

        form = _assert_mobile_request(
            request,
            post,
        )

        assert form["count"] == "20"

        if len(requests) == 1:
            assert "pcursor" not in form

            return _page(
                range(20),
                "first-post-page-2",
            )

        if len(requests) == 2:
            assert form["pcursor"] == "first-post-page-2"

            assert form["llsid"] == _form(requests[0])["llsid"]

            return _page(
                range(
                    18,
                    35,
                ),
                "no_more",
            )

        assert "pcursor" not in form

        return _page(
            range(2),
            "no_more",
        )

    mobile_keyword_cli(
        handler,
    )

    assert (
        cli.main(
            [
                *_arguments(
                    tmp_path,
                ),
                "--delay",
                "0.25",
            ]
        )
        == 0
    )

    assert keywords == [
        KEYWORD,
    ]

    assert (
        len(
            requests,
        )
        == 3
    )

    aggregate = _read_export(
        tmp_path,
        posts,
    )

    assert aggregate["limite_comentarios_por_post"] is None

    assert aggregate["total_comentarios_coletados"] == 37

    assert aggregate["total_posts_com_erro"] == 0

    assert aggregate["complete"] is True

    assert [comment["id"] for comment in (aggregate["posts"][0]["comentarios"])] == [
        str(index) for index in range(35)
    ]

    assert [comment["id"] for comment in (aggregate["posts"][1]["comentarios"])] == [
        "0",
        "1",
    ]

    assert not list(tmp_path.glob("*_comentarios.coleta.json"))


def test_keyword_comments_limit_50_uses_three_bounded_pages(
    monkeypatch: pytest.MonkeyPatch,
    mobile_keyword_cli: Callable,
    tmp_path: Path,
) -> None:
    posts = [
        _post(
            "123",
            "456",
            "autor_um",
        )
    ]

    _mock_search(
        monkeypatch,
        posts,
    )

    requests: list[httpx.Request] = []

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        requests.append(
            request,
        )

        assert len(requests) <= 3

        form = _assert_mobile_request(
            request,
            posts[0],
        )

        assert form["count"] == ("10" if len(requests) == 3 else "20")

        if len(requests) == 1:
            assert "pcursor" not in form

            return _page(
                range(20),
                "page-2",
            )

        assert form["pcursor"] == f"page-{len(requests)}"

        if len(requests) == 2:
            return _page(
                range(
                    20,
                    40,
                ),
                "page-3",
            )

        return _page(
            range(
                40,
                65,
            ),
            "page-4",
        )

    mobile_keyword_cli(
        handler,
    )

    assert (
        cli.main(
            _arguments(
                tmp_path,
                limit="50",
            )
        )
        == 0
    )

    assert (
        len(
            requests,
        )
        == 3
    )

    aggregate = _read_export(
        tmp_path,
        posts,
    )

    assert aggregate["limite_comentarios_por_post"] == 50

    assert aggregate["total_comentarios_coletados"] == 50

    assert aggregate["complete"] is True

    assert [comment["id"] for comment in (aggregate["posts"][0]["comentarios"])] == [
        str(index) for index in range(50)
    ]

    assert not list(tmp_path.glob("*_comentarios.coleta.json"))


def test_keyword_comments_defaults_to_20_per_post(
    monkeypatch: pytest.MonkeyPatch,
    mobile_keyword_cli: Callable,
    tmp_path: Path,
) -> None:
    posts = [
        _post(
            "123",
            "456",
            "autor_um",
        ),
        _post(
            "321",
            "654",
            "autor_dois",
        ),
    ]

    _mock_search(
        monkeypatch,
        posts,
    )

    requests: list[httpx.Request] = []

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        requests.append(
            request,
        )

        assert len(requests) <= 2

        form = _assert_mobile_request(
            request,
            posts[len(requests) - 1],
        )

        assert form["count"] == "20"

        assert "pcursor" not in form

        return _page(
            range(25),
            "more-pages",
        )

    mobile_keyword_cli(
        handler,
    )

    assert (
        cli.main(
            _arguments(
                tmp_path,
                limit=None,
            )
        )
        == 0
    )

    aggregate = _read_export(
        tmp_path,
        posts,
    )

    assert aggregate["limite_comentarios_por_post"] == 20

    assert aggregate["total_comentarios_coletados"] == 40

    assert [post["quantidade"] for post in aggregate["posts"]] == [
        20,
        20,
    ]

    assert not list(tmp_path.glob("*_comentarios.coleta.json"))

    defaults = cli._criar_parser_buscar().parse_args(
        [
            KEYWORD,
            "--with-comments",
        ]
    )

    assert defaults.max_comments == 20

    assert defaults.request_interval == 2


def test_keyword_comments_preserves_partial_failure_and_continues_next_post(
    monkeypatch: pytest.MonkeyPatch,
    mobile_keyword_cli: Callable,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    posts = [
        _post(
            "123",
            "456",
            "autor_um",
        ),
        _post(
            "321",
            "654",
            "autor_dois",
        ),
    ]

    _mock_search(
        monkeypatch,
        posts,
    )

    requests: list[httpx.Request] = []

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        requests.append(
            request,
        )

        assert len(requests) <= 5

        post = posts[0] if len(requests) <= 4 else posts[1]

        form = _assert_mobile_request(
            request,
            post,
        )

        if len(requests) == 1:
            assert "pcursor" not in form

            return _page(
                range(20),
                "failed-page",
            )

        if len(requests) <= 4:
            assert form["pcursor"] == "failed-page"

            assert form["llsid"] == _form(requests[0])["llsid"]

            return httpx.Response(
                501,
                json={"error_msg": (f"synthetic-token {request.url}")},
            )

        assert "pcursor" not in form

        return _page(
            range(2),
            "no_more",
        )

    mobile_keyword_cli(
        handler,
    )

    assert (
        cli.main(
            _arguments(
                tmp_path,
            )
        )
        == 1
    )

    assert (
        len(
            requests,
        )
        == 5
    )

    aggregate = _read_export(
        tmp_path,
        posts,
    )

    assert aggregate["total_comentarios_coletados"] == 22

    assert aggregate["total_posts_com_erro"] == 1

    assert aggregate["complete"] is False

    assert aggregate["posts"][0]["quantidade"] == 20

    assert "501" in aggregate["posts"][0]["erro"]

    assert aggregate["posts"][1]["quantidade"] == 2

    assert "erro" not in aggregate["posts"][1]

    checkpoint_path = tmp_path / "123_comentarios.coleta.json"

    checkpoint_text = checkpoint_path.read_text(
        encoding="utf-8",
    )

    checkpoint = json.loads(
        checkpoint_text,
    )

    assert checkpoint["photo_id"] == "123"

    assert checkpoint["user_id"] == "456"

    assert checkpoint["pcursor"] == "failed-page"

    assert checkpoint["complete"] is False

    assert checkpoint["comments"] == [_comment(index) for index in range(20)]

    assert not (tmp_path / "321_comentarios.coleta.json").exists()

    exported_text = "\n".join(
        path.read_text(
            encoding="utf-8",
        )
        for path in tmp_path.glob("*.json")
    )

    for value in SESSION_VALUES:
        assert value not in exported_text

        assert value not in caplog.text


def test_keyword_listing_without_comments_keeps_the_existing_export(
    monkeypatch: pytest.MonkeyPatch,
    mobile_keyword_cli: Callable,
    tmp_path: Path,
) -> None:
    posts = [
        _post(
            "123",
            "456",
            "autor_um",
        ),
        _post(
            "321",
            "654",
            "autor_dois",
        ),
    ]

    keywords = _mock_search(
        monkeypatch,
        posts,
        expected_delay=0.5,
    )

    def reject_auth_provider() -> None:
        raise AssertionError("Listing posts must not prepare comment authentication.")

    monkeypatch.setattr(
        cli,
        "_criar_auth_provider_mobile",
        reject_auth_provider,
    )

    assert (
        cli.main(
            [
                "buscar",
                KEYWORD,
                "--output-dir",
                str(tmp_path),
                "--delay",
                "0.5",
            ]
        )
        == 0
    )

    assert keywords == [
        KEYWORD,
    ]

    assert [path.name for path in tmp_path.iterdir()] == [f"{OUTPUT_NAME}.json"]

    listed = json.loads(
        (tmp_path / f"{OUTPUT_NAME}.json").read_text(
            encoding="utf-8",
        )
    )

    assert isinstance(
        listed,
        list,
    )

    assert [post["id"] for post in listed] == [
        "123",
        "321",
    ]

    assert [post["texto"] for post in listed] == [post["caption"] for post in posts]


def test_keyword_comments_collects_duplicate_search_posts_once(
    monkeypatch: pytest.MonkeyPatch,
    mobile_keyword_cli: Callable,
    tmp_path: Path,
) -> None:
    post = _post(
        "123",
        "456",
        "autor_um",
    )

    _mock_search(
        monkeypatch,
        [
            post,
            dict(post),
        ],
    )

    requests: list[httpx.Request] = []

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        requests.append(
            request,
        )

        assert len(requests) == 1

        _assert_mobile_request(
            request,
            post,
        )

        return _page(
            range(2),
            "no_more",
        )

    mobile_keyword_cli(
        handler,
    )

    assert (
        cli.main(
            _arguments(
                tmp_path,
            )
        )
        == 0
    )

    listed = json.loads(
        (tmp_path / f"{OUTPUT_NAME}.json").read_text(
            encoding="utf-8",
        )
    )

    assert (
        len(
            listed,
        )
        == 2
    )

    aggregate = json.loads(
        (tmp_path / f"{OUTPUT_NAME}_comentarios.json").read_text(
            encoding="utf-8",
        )
    )

    assert aggregate["total_posts_processados"] == 1

    assert aggregate["total_comentarios_coletados"] == 2

    assert aggregate["total_posts_com_erro"] == 0

    assert aggregate["complete"] is True

    assert (
        len(
            aggregate["posts"],
        )
        == 1
    )

    assert aggregate["posts"][0]["photo_id"] == "123"


def test_keyword_comments_empty_search_is_complete_without_comment_requests(
    monkeypatch: pytest.MonkeyPatch,
    mobile_keyword_cli: Callable,
    tmp_path: Path,
) -> None:
    _mock_search(
        monkeypatch,
        [],
    )

    assert (
        cli.main(
            _arguments(
                tmp_path,
            )
        )
        == 0
    )

    aggregate = _read_export(
        tmp_path,
        [],
    )

    assert aggregate["total_posts_processados"] == 0

    assert aggregate["total_comentarios_coletados"] == 0

    assert aggregate["total_posts_com_erro"] == 0

    assert aggregate["complete"] is True

    assert aggregate["posts"] == []

    assert {path.name for path in tmp_path.iterdir()} == {
        f"{OUTPUT_NAME}.json",
        f"{OUTPUT_NAME}_comentarios.json",
    }


@pytest.mark.parametrize(
    ("option", "value"),
    [
        (
            "--max-comments",
            "0",
        ),
        (
            "--max-comments",
            "-1",
        ),
        (
            "--max-comments",
            "1.5",
        ),
        (
            "--request-interval",
            "-1",
        ),
        (
            "--request-interval",
            "nan",
        ),
        (
            "--request-interval",
            "inf",
        ),
    ],
)
def test_keyword_comments_rejects_invalid_limits_and_intervals(
    mobile_keyword_cli: Callable,
    option: str,
    value: str,
) -> None:
    with pytest.raises(
        SystemExit,
    ) as exc_info:
        cli.main(
            [
                "buscar",
                KEYWORD,
                "--with-comments",
                option,
                value,
            ]
        )

    assert exc_info.value.code == 2

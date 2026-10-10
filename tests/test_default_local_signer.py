from __future__ import annotations

import base64
import json
import os
import re
from collections.abc import Callable, Iterator
from importlib.resources import files
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest

from kwai_collector import cli, cli_parsers, config
from kwai_collector.config import Settings
from kwai_collector.security.android_profile_mobile_request_provider import (
    AndroidProfileMobileRequestProvider,
)
from kwai_collector.security.comment_list_v2_request_provider import (
    CommentListV2RequestProvider,
)
from kwai_collector.security.comment_list_v2_signer import (
    KwaiLite103CommentListV2Signer,
)
from kwai_collector.security.http_mobile_request_provider import (
    HttpMobileRequestProvider,
)
from kwai_collector.security.mobile_request_provider_factory import (
    criar_mobile_request_provider,
)
from kwai_collector.security.signature_provider import PreparedMobileRequest

PHOTO_ID = "1234567890"
POST_URL = f"https://www.kwai.com/@public_profile/video/{PHOTO_ID}"
Handler = Callable[[httpx.Request], httpx.Response]


@pytest.fixture(autouse=True)
def fresh_defaults(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Settings:
    """Use the settings a new checkout receives, including the real auth factory."""
    for name in tuple(os.environ):
        if name.upper().startswith("KWAI_"):
            monkeypatch.delenv(name)
    monkeypatch.chdir(tmp_path)
    assert not Path(".env").exists()
    defaults = Settings()
    for module in (cli, cli_parsers, config):
        monkeypatch.setattr(module, "settings", defaults)
    return defaults


@pytest.fixture
def intercept_http(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[Callable[[Handler], list[httpx.Request]]]:
    original_client = httpx.Client
    clients: list[httpx.Client] = []

    def install(handler: Handler) -> list[httpx.Request]:
        requests: list[httpx.Request] = []

        def record(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return handler(request)

        def create_client(*args: Any, **kwargs: Any) -> httpx.Client:
            kwargs["transport"] = httpx.MockTransport(record)
            kwargs["trust_env"] = False
            client = original_client(*args, **kwargs)
            clients.append(client)
            return client

        def unexpected_request(*args: Any, **kwargs: Any) -> None:
            pytest.fail("The paginated mobile CLI must use its mocked HTTP client.")

        monkeypatch.setattr(httpx, "Client", create_client)
        monkeypatch.setattr(httpx, "get", unexpected_request)
        monkeypatch.setattr(httpx, "post", unexpected_request)
        return requests

    yield install
    for client in clients:
        client.close()


def _form(request: httpx.Request) -> dict[str, str]:
    return {
        key: values[-1]
        for key, values in parse_qs(
            request.content.decode(), keep_blank_values=True
        ).items()
    }


def _comment(index: int) -> dict[str, object]:
    return {
        "commentId": str(index),
        "userName": f"Public user {index}",
        "content": f"Public comment {index}",
        "commentLikeCount": index,
    }


@pytest.mark.parametrize(
    ("limit", "page_ranges", "page_counts", "expected_count"),
    [
        ("50", [(0, 20), (20, 40), (40, 50)], ["20", "20", "10"], 50),
        ("todos", [(0, 20), (18, 38), (36, 43)], ["20", "20", "20"], 43),
    ],
)
def test_fresh_default_cli_signs_and_paginates_without_credentials(
    intercept_http: Callable[[Handler], list[httpx.Request]],
    tmp_path: Path,
    limit: str,
    page_ranges: list[tuple[int, int]],
    page_counts: list[str],
    expected_count: int,
) -> None:
    expected_cursors = [None, "page-2", "page-3"]
    page_index = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal page_index
        assert request.method == "POST"
        assert request.url.host == "api2-us.kwaipros.com"
        assert request.url.path == "/rest/o/comment/list/v2"
        form = _form(request)
        assert form.get("pcursor") == expected_cursors[page_index]
        assert form["count"] == page_counts[page_index]
        assert form["photoId"] == PHOTO_ID
        assert form["user_id"] == "public_profile"
        start, stop = page_ranges[page_index]
        page_index += 1
        return httpx.Response(
            200,
            json={
                "result": 1,
                "rootComments": [_comment(index) for index in range(start, stop)],
                "pcursor": (
                    f"page-{page_index + 1}"
                    if page_index < 3 or limit == "50"
                    else "no_more"
                ),
            },
        )

    requests = intercept_http(handler)
    assert (
        cli.main(
            [
                "comentarios",
                POST_URL,
                "--max-comments",
                limit,
                "--request-interval",
                "0",
                "--output-dir",
                str(tmp_path),
            ]
        )
        == 0
    )
    assert len(requests) == 3
    saved = json.loads((tmp_path / f"{PHOTO_ID}_comentarios.json").read_text("utf-8"))
    assert [comment["id"] for comment in saved] == [
        str(index) for index in range(expected_count)
    ]
    assert saved[0]["texto"] == "Public comment 0"
    assert all(comment["postagem_url"] == POST_URL for comment in saved)
    assert not (tmp_path / f"{PHOTO_ID}_comentarios.coleta.json").exists()

    signatures: list[str] = []
    native_signatures: list[str] = []
    sessions: set[str] = set()
    forbidden = {
        "token",
        "passToken",
        "kwaipro.api_st",
        "client_salt",
        "did",
        "egid",
        "session_id",
    }
    for request in requests:
        query = dict(request.url.params)
        form = _form(request)
        assert forbidden.isdisjoint(query)
        assert forbidden.isdisjoint(form)
        assert "Cookie" not in request.headers
        assert "Authorization" not in request.headers
        assert "sig" not in query
        assert "__NS_sig3" not in form
        assert "__NStokensig" not in query and "__NStokensig" not in form
        assert re.fullmatch(r"[0-9a-f]{32}", form["sig"])
        native_signatures.append(form["sig"])
        sig3 = query["__NS_sig3"]
        decoded = base64.urlsafe_b64decode(sig3 + "=")
        assert len(decoded) == 56
        assert re.fullmatch(rb"[0-9a-f]{48}", decoded[8:])
        signatures.append(sig3)
        assert "llsid" not in query
        assert form["llsid"].isdigit()
        sessions.add(form["llsid"])
        assert query["pkg"] == "kwai.lite.video"
        assert query["appver"] == "10.3.20.540101"
        assert query["timestamp"].isdigit()
        assert query.keys().isdisjoint(form)
    assert len(set(signatures)) == 3
    assert len(set(native_signatures)) == 3
    assert len(sessions) == 1


def test_default_provider_uses_the_importable_bundled_signer_material() -> None:
    provider = cli._criar_auth_provider_mobile()
    assert isinstance(provider, AndroidProfileMobileRequestProvider)
    assert isinstance(provider.delegate, CommentListV2RequestProvider)
    assert isinstance(provider.delegate.signer, KwaiLite103CommentListV2Signer)
    material = files("kwai_collector.security").joinpath(
        "kwai_lite_103_sig3_material.bin"
    )
    assert material.is_file()
    assert len(material.read_bytes()) == 151616


def test_explicit_external_endpoint_overrides_the_default_local_signer(
    fresh_defaults: Settings,
    intercept_http: Callable[[Handler], list[httpx.Request]],
) -> None:
    fresh_defaults.mobile_auth_endpoint = "https://signer.example/prepare"
    fresh_defaults.mobile_auth_token = "service-test-token"

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://signer.example/prepare"
        assert request.headers["Authorization"] == "Bearer service-test-token"
        payload = json.loads(request.content)
        assert payload["body"] == {"photoId": PHOTO_ID}
        return httpx.Response(
            200,
            json={
                "query": {"external": "query"},
                "body": {"external": "body"},
                "headers": {"X-External": "prepared"},
            },
        )

    requests = intercept_http(handler)
    provider = cli._criar_auth_provider_mobile()
    assert isinstance(provider, AndroidProfileMobileRequestProvider)
    assert isinstance(provider.delegate, HttpMobileRequestProvider)
    prepared = provider.prepare(query={}, body={"photoId": PHOTO_ID}, headers={})
    assert len(requests) == 1
    assert prepared == PreparedMobileRequest(
        query={"external": "query"},
        body={"external": "body"},
        headers={"X-External": "prepared"},
    )


def test_explicit_provider_injection_remains_supported() -> None:
    class InjectedProvider:
        def prepare(
            self,
            *,
            query: dict[str, str],
            body: dict[str, str],
            headers: dict[str, str],
        ) -> PreparedMobileRequest:
            assert query["os"] == "android"
            assert body["photoId"] == PHOTO_ID
            return PreparedMobileRequest(query, {**body, "injected": "yes"}, headers)

    provider = criar_mobile_request_provider(delegate=InjectedProvider())
    prepared = provider.prepare(query={}, body={"photoId": PHOTO_ID}, headers={})
    assert prepared.body == {"photoId": PHOTO_ID, "injected": "yes"}

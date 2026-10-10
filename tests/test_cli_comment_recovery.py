from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest

from kwai_collector import cli
from kwai_collector.config import Settings
from kwai_collector.security.signature_provider import PreparedMobileRequest

PHOTO_ID = "1234567890"
USER_ID = "987654321"
POST_URL = f"https://www.kwai.com/@perfil_sintetico/video/{PHOTO_ID}"


class FakeMobileRequestProvider:
    """Provider sintético usado somente nos testes de recuperação."""

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


def _comment(index: int) -> dict[str, object]:
    return {
        "commentId": str(index),
        "userName": f"Usuario {index}",
        "kwaiid": f"usuario{index}",
        "content": f"Comentario {index}",
        "commentLikeCount": index,
    }


def _form(request: httpx.Request) -> dict[str, str]:
    return {
        key: values[0] for key, values in parse_qs(request.content.decode()).items()
    }


@pytest.fixture
def safe_mobile_cli(monkeypatch):
    """Isola configurações locais e usa autenticação sintética nos testes."""
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
            "client_salt": "synthetic-salt",
        },
        mobile_header_fields={
            "X-Test-Session": "synthetic-header",
        },
        mobile_auth_endpoint=None,
        mobile_auth_token=None,
        max_tentativas=3,
        backoff_base=0,
        delay=0,
        mobile_page_delay=0,
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

    def install_transport(handler):
        transport = httpx.MockTransport(handler)

        def mocked_client(*args, **kwargs):
            kwargs["transport"] = transport
            return original_client(*args, **kwargs)

        monkeypatch.setattr(
            httpx,
            "Client",
            mocked_client,
        )

    return install_transport


def _arguments(
    output_dir: Path,
    *,
    limit: str = "todos",
) -> list[str]:
    return [
        "comentarios",
        POST_URL,
        "--user-id",
        USER_ID,
        "--max-comments",
        limit,
        "--output-dir",
        str(output_dir),
    ]


def _interrupt_collection(
    install_transport,
    output_dir: Path,
) -> list[httpx.Request]:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)

        assert request.method == "POST"
        assert request.url.host == "api2-us.kwaipros.com"
        assert request.url.path == "/rest/o/comment/list/v2"

        if len(requests) == 1:
            return httpx.Response(
                200,
                json={
                    "result": 1,
                    "rootComments": [_comment(index) for index in range(20)],
                    "pcursor": "next-page",
                },
            )

        return httpx.Response(
            501,
            json={
                "error_msg": "Falha temporaria",
            },
        )

    install_transport(handler)

    assert cli.main(_arguments(output_dir)) == 1
    assert len(requests) == 4

    return requests


def test_cli_preserves_comments_and_safe_checkpoint_after_page_failure(
    safe_mobile_cli,
    tmp_path,
    caplog,
):
    requests = _interrupt_collection(
        safe_mobile_cli,
        tmp_path,
    )

    output_path = tmp_path / f"{PHOTO_ID}_comentarios.json"

    saved = json.loads(
        output_path.read_text(
            encoding="utf-8",
        )
    )

    assert [comment["id"] for comment in saved] == [str(index) for index in range(20)]

    assert saved[0]["texto"] == "Comentario 0"
    assert saved[0]["postagem_url"] == POST_URL

    checkpoint_path = tmp_path / f"{PHOTO_ID}_comentarios.coleta.json"

    checkpoint_text = checkpoint_path.read_text(
        encoding="utf-8",
    )

    checkpoint = json.loads(checkpoint_text)

    assert set(checkpoint) == {
        "version",
        "photo_id",
        "user_id",
        "llsid",
        "pcursor",
        "comments",
        "complete",
    }

    assert checkpoint["version"] == 1
    assert checkpoint["photo_id"] == PHOTO_ID
    assert checkpoint["user_id"] == USER_ID
    assert checkpoint["pcursor"] == "next-page"
    assert checkpoint["complete"] is False

    assert checkpoint["comments"] == [_comment(index) for index in range(20)]

    first_form = _form(requests[0])

    assert checkpoint["llsid"] == first_form["llsid"]

    forbidden_values = (
        "synthetic-token",
        "synthetic-pass-token",
        "synthetic-api-st",
        "synthetic-salt",
        "synthetic-header",
        "synthetic-device",
        "synthetic-session",
    )

    for forbidden in forbidden_values:
        assert forbidden not in checkpoint_text
        assert forbidden not in caplog.text

    assert "20" in caplog.text

    assert any(
        word in caplog.text.lower()
        for word in (
            "incompleta",
            "interrompida",
            "parcial",
        )
    )

    retries = [_form(request) for request in requests[1:]]

    assert all(form["pcursor"] == "next-page" for form in retries)

    assert all(form["llsid"] == first_form["llsid"] for form in retries)


@pytest.mark.parametrize(
    ("limit", "expected_count"),
    [
        ("todos", 40),
        ("30", 30),
    ],
)
def test_cli_resumes_saved_cursor_and_deduplicates_with_new_limit(
    safe_mobile_cli,
    tmp_path,
    limit,
    expected_count,
):
    _interrupt_collection(
        safe_mobile_cli,
        tmp_path,
    )

    checkpoint_path = tmp_path / f"{PHOTO_ID}_comentarios.coleta.json"

    checkpoint = json.loads(
        checkpoint_path.read_text(
            encoding="utf-8",
        )
    )

    resumed_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        resumed_requests.append(request)

        form = _form(request)

        assert form["pcursor"] == checkpoint["pcursor"]
        assert form["llsid"] == checkpoint["llsid"]
        assert form["photoId"] == PHOTO_ID
        assert form["user_id"] == USER_ID

        expected_page_size = "20" if limit == "todos" else "10"

        assert form["count"] == expected_page_size

        return httpx.Response(
            200,
            json={
                "result": 1,
                "rootComments": [_comment(index) for index in range(18, 40)],
                "pcursor": "no_more",
            },
        )

    safe_mobile_cli(handler)

    result = cli.main(
        [
            *_arguments(
                tmp_path,
                limit=limit,
            ),
            "--resume",
        ]
    )

    assert result == 0
    assert len(resumed_requests) == 1

    resumed_form = _form(resumed_requests[0])

    assert resumed_form["pcursor"] == "next-page"
    assert resumed_form["llsid"] == checkpoint["llsid"]

    saved_path = tmp_path / f"{PHOTO_ID}_comentarios.json"

    saved = json.loads(
        saved_path.read_text(
            encoding="utf-8",
        )
    )

    assert len(saved) == expected_count

    assert [comment["id"] for comment in saved] == [
        str(index) for index in range(expected_count)
    ]

    assert not checkpoint_path.exists()

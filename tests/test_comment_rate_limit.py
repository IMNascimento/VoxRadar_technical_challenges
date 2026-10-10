from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest

from kwai_collector import cli
from kwai_collector.clients.comment_collection_progress import (
    CommentCollectionInterrupted,
)
from kwai_collector.clients.live_comment_client import LiveCommentClient
from kwai_collector.clients.request_rate_limiter import (
    RequestRateLimiter,
    parse_retry_after,
)
from kwai_collector.config import Settings
from kwai_collector.security.signature_provider import PreparedMobileRequest


class VirtualTime:
    def __init__(self) -> None:
        self.now = 0.0
        self.waits: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.waits.append(seconds)
        self.now += seconds


class RecordingMobileRequestProvider:
    """Registra quando cada requisição é preparada nos testes."""

    def __init__(self, clock: VirtualTime) -> None:
        self.clock = clock
        self.prepared_at: list[float] = []

    def prepare(
        self,
        *,
        query: dict[str, str],
        body: dict[str, str],
        headers: dict[str, str],
    ) -> PreparedMobileRequest:
        self.prepared_at.append(self.clock.now)

        return PreparedMobileRequest(
            query=dict(query),
            body=dict(body),
            headers=dict(headers),
        )


@pytest.fixture
def virtual_time(
    monkeypatch: pytest.MonkeyPatch,
) -> VirtualTime:
    clock = VirtualTime()

    monkeypatch.setattr(
        "kwai_collector.clients.live_comment_client.monotonic",
        lambda: clock.now,
    )

    monkeypatch.setattr(
        "kwai_collector.clients.live_comment_client.sleep",
        clock.sleep,
    )

    return clock


def test_rate_limit_covers_pages_retries_and_request_preparation(
    virtual_time: VirtualTime,
) -> None:
    provider = RecordingMobileRequestProvider(
        virtual_time,
    )

    sent: list[tuple[float, httpx.Request]] = []

    def handle(
        request: httpx.Request,
    ) -> httpx.Response:
        assert request.url.path == "/rest/o/comment/list/v2"

        sent.append(
            (
                virtual_time.now,
                request,
            )
        )

        if len(sent) == 2:
            return httpx.Response(501)

        return httpx.Response(
            200,
            json={
                "result": 1,
                "rootComments": [
                    {
                        "commentId": str(len(sent)),
                        "content": "root",
                    }
                ],
                "pcursor": ("next" if len(sent) == 1 else "no_more"),
            },
        )

    with httpx.Client(
        transport=httpx.MockTransport(handle),
    ) as http_client:
        client = LiveCommentClient(
            provider,
            client=http_client,
            page_delay=2,
            backoff_base=1,
        )

        comments = client.fetch_root_comments(
            "post",
            "author",
            None,
        )

    assert len(comments) == 2

    assert [time for time, _ in sent] == [
        0,
        2,
        4,
    ]

    assert provider.prepared_at == [
        0,
        2,
        4,
    ]

    forms = [parse_qs(request.content.decode()) for _, request in sent]

    assert forms[1] == forms[2]


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("5", 5),
        ("125", 125),
        ("invalid", 2),
    ],
)
def test_retry_after_is_respected_without_shortening_long_waits(
    virtual_time: VirtualTime,
    header: str,
    expected: int,
) -> None:
    provider = RecordingMobileRequestProvider(
        virtual_time,
    )

    times: list[float] = []

    def handle(
        request: httpx.Request,
    ) -> httpx.Response:
        times.append(virtual_time.now)

        if len(times) == 1:
            return httpx.Response(
                429,
                headers={
                    "Retry-After": header,
                },
            )

        return httpx.Response(
            200,
            json={
                "result": 1,
                "rootComments": [],
                "pcursor": "no_more",
            },
        )

    with httpx.Client(
        transport=httpx.MockTransport(handle),
    ) as http_client:
        client = LiveCommentClient(
            provider,
            client=http_client,
            page_delay=2,
            backoff_base=1,
        )

        assert (
            client.fetch_root_comments(
                "post",
                "author",
                None,
            )
            == []
        )

    assert times == [
        0,
        expected,
    ]

    assert provider.prepared_at == [
        0,
        expected,
    ]

    assert max(virtual_time.waits) <= 60


def test_cooldown_survives_retry_exhaustion_for_the_next_post(
    virtual_time: VirtualTime,
) -> None:
    times: list[float] = []

    def handle(
        request: httpx.Request,
    ) -> httpx.Response:
        times.append(virtual_time.now)

        if len(times) == 1:
            return httpx.Response(
                429,
                headers={
                    "Retry-After": "10",
                },
            )

        return httpx.Response(
            200,
            json={
                "result": 1,
                "rootComments": [],
                "pcursor": "no_more",
            },
        )

    with httpx.Client(
        transport=httpx.MockTransport(handle),
    ) as http_client:
        client = LiveCommentClient(
            RecordingMobileRequestProvider(
                virtual_time,
            ),
            client=http_client,
            max_attempts=1,
            page_delay=2,
        )

        with pytest.raises(CommentCollectionInterrupted):
            client.fetch_root_comments(
                "first",
                "author",
                None,
            )

        assert (
            client.fetch_root_comments(
                "second",
                "author",
                None,
            )
            == []
        )

    assert times == [
        0,
        10,
    ]


def test_retry_after_http_date_and_invalid_values() -> None:
    now = datetime(
        2026,
        10,
        7,
        12,
        tzinfo=UTC,
    )

    assert (
        parse_retry_after(
            "Wed, 07 Oct 2026 12:00:07 GMT",
            now=now,
        )
        == 7
    )

    assert (
        parse_retry_after(
            "Wed, 07 Oct 2026 11:00:00 GMT",
            now=now,
        )
        == 0
    )

    assert (
        parse_retry_after(
            None,
            now=now,
        )
        is None
    )

    assert (
        parse_retry_after(
            "garbage",
            now=now,
        )
        is None
    )

    assert (
        parse_retry_after(
            "nan",
            now=now,
        )
        is None
    )

    assert (
        parse_retry_after(
            "inf",
            now=now,
        )
        is None
    )


def test_rate_limit_counts_request_time_and_uses_remaining_interval() -> None:
    clock = VirtualTime()

    limiter = RequestRateLimiter(
        2,
        clock=lambda: clock.now,
        sleeper=clock.sleep,
    )

    limiter.wait_before_request()

    clock.now += 0.75

    limiter.wait_before_request()

    assert clock.waits == [
        1.25,
    ]

    assert clock.now == 2


def test_spacing_uses_send_time_and_is_shared_between_posts(
    virtual_time: VirtualTime,
) -> None:
    class SlowProvider(RecordingMobileRequestProvider):
        def prepare(
            self,
            *,
            query: dict[str, str],
            body: dict[str, str],
            headers: dict[str, str],
        ) -> PreparedMobileRequest:
            prepared = super().prepare(
                query=query,
                body=body,
                headers=headers,
            )

            if len(self.prepared_at) == 1:
                virtual_time.now += 0.4
            else:
                virtual_time.now += 0.1

            return prepared

    provider = SlowProvider(
        virtual_time,
    )

    times: list[float] = []

    def handle(
        request: httpx.Request,
    ) -> httpx.Response:
        times.append(virtual_time.now)

        return httpx.Response(
            200,
            json={
                "result": 1,
                "rootComments": [],
                "pcursor": "no_more",
            },
        )

    with httpx.Client(
        transport=httpx.MockTransport(handle),
    ) as http_client:
        client = LiveCommentClient(
            provider,
            client=http_client,
            page_delay=2,
        )

        client.fetch_root_comments(
            "first",
            "author",
            None,
        )

        client.fetch_root_comments(
            "second",
            "author",
            None,
        )

    assert times == pytest.approx(
        [
            0.4,
            2.5,
        ]
    )

    assert provider.prepared_at == pytest.approx(
        [
            0,
            2.4,
        ]
    )

    assert times[1] - times[0] >= 2


@pytest.mark.parametrize(
    "value",
    [
        -1,
        float("inf"),
        float("nan"),
    ],
)
def test_invalid_interval_is_rejected(
    value: float,
) -> None:
    with pytest.raises(ValueError):
        RequestRateLimiter(value)

    with pytest.raises(ValueError):
        Settings(
            _env_file=None,
            mobile_page_delay=value,
        )


def test_cli_interval_collects_roots_only(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    virtual_time: VirtualTime,
) -> None:
    settings = Settings(
        _env_file=None,
        cookie=None,
        mobile_query_fields={},
        mobile_body_fields={},
        mobile_header_fields={},
        mobile_auth_endpoint=None,
        mobile_auth_token=None,
        mobile_page_delay=0,
    )

    monkeypatch.setattr(
        cli,
        "settings",
        settings,
    )

    provider = RecordingMobileRequestProvider(
        virtual_time,
    )

    monkeypatch.setattr(
        cli,
        "_criar_auth_provider_mobile",
        lambda: provider,
    )

    times: list[float] = []

    def handle(
        request: httpx.Request,
    ) -> httpx.Response:
        assert request.url.path == "/rest/o/comment/list/v2"

        times.append(virtual_time.now)

        return httpx.Response(
            200,
            json={
                "result": 1,
                "rootComments": [
                    {
                        "commentId": str(len(times)),
                        "content": "main",
                        "subCommentCount": 10,
                        "subComments": [
                            {
                                "commentId": "reply",
                                "content": "reply",
                            }
                        ],
                    }
                ],
                "pcursor": ("next" if len(times) == 1 else "no_more"),
            },
        )

    original_client = httpx.Client

    def mocked_client(
        *args,
        **kwargs,
    ):
        kwargs["transport"] = httpx.MockTransport(handle)

        return original_client(
            *args,
            **kwargs,
        )

    monkeypatch.setattr(
        httpx,
        "Client",
        mocked_client,
    )

    result = cli.main(
        [
            "comentarios",
            "https://www.kwai.com/@synthetic/video/123",
            "--max-comments",
            "todos",
            "--request-interval",
            "3",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert result == 0

    assert times == [
        0,
        3,
    ]

    saved_path = tmp_path / "123_comentarios.json"

    saved = json.loads(
        saved_path.read_text(
            encoding="utf-8",
        )
    )

    assert [comment["id"] for comment in saved] == [
        "1",
        "2",
    ]

    assert not (tmp_path / "123_comentarios.coleta.json").exists()


@pytest.mark.parametrize(
    "command",
    [
        "comentarios",
        "coletar",
    ],
)
@pytest.mark.parametrize(
    "value",
    [
        "-1",
        "inf",
        "nan",
    ],
)
def test_cli_rejects_invalid_interval(
    command: str,
    value: str,
) -> None:
    with pytest.raises(SystemExit):
        cli.main(
            [
                command,
                "synthetic",
                "--request-interval",
                value,
            ]
        )

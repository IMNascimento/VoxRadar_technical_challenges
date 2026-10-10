from __future__ import annotations

from urllib.parse import parse_qs

import httpx
import pytest

from kwai_collector.clients.comment_collection_progress import (
    CommentCollectionInterrupted,
    CommentCollectionProgress,
)
from kwai_collector.clients.live_comment_client import LiveCommentClient
from kwai_collector.security.signature_provider import PreparedMobileRequest


class SigningProvider:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def prepare(
        self,
        *,
        query: dict[str, str],
        body: dict[str, str],
        headers: dict[str, str],
    ) -> PreparedMobileRequest:
        self.calls.append(dict(body))
        query["__NS_sig3"] = f"fresh-signature-{len(self.calls)}"
        query["timestamp"] = str(len(self.calls))
        return PreparedMobileRequest(query=query, body=body, headers=headers)


def body_fields(request: httpx.Request) -> dict[str, str]:
    return {
        key: values[-1]
        for key, values in parse_qs(
            request.content.decode(), keep_blank_values=True
        ).items()
    }


def comments(start: int, end: int) -> list[dict[str, str]]:
    return [
        {"commentId": str(number), "content": f"comment {number}"}
        for number in range(start, end)
    ]


def success(items: list[dict[str, str]], cursor: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={"result": 1, "rootComments": items, "pcursor": cursor},
    )


@pytest.fixture
def delays(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    recorded: list[float] = []
    now = [0.0]

    def fake_sleep(delay: float) -> None:
        recorded.append(delay)
        now[0] += delay

    monkeypatch.setattr(
        "kwai_collector.clients.live_comment_client.monotonic", lambda: now[0]
    )
    monkeypatch.setattr("kwai_collector.clients.live_comment_client.sleep", fake_sleep)
    return recorded


def test_retry_501_signs_again_on_same_page_and_cursor(
    delays: list[float],
) -> None:
    provider = SigningProvider()
    requests: list[httpx.Request] = []
    progress: list[CommentCollectionProgress] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(501, text="not implemented")
        return success(comments(1, 3), "no_more")

    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        client = LiveCommentClient(auth_provider=provider, client=http_client)
        result = client.fetch_root_comments(
            "photo", "user", None, on_progress=progress.append
        )

    assert result == comments(1, 3)
    assert provider.calls[0] == provider.calls[1]
    assert requests[0].url.params["__NS_sig3"] != requests[1].url.params["__NS_sig3"]
    assert requests[0].url.params["timestamp"] != requests[1].url.params["timestamp"]
    assert delays == [1.0]
    assert len(progress) == 1
    assert progress[0].complete


def test_retry_exhaustion_preserves_successful_page_and_failed_cursor(
    delays: list[float],
) -> None:
    provider = SigningProvider()
    progress: list[CommentCollectionProgress] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if not body_fields(request).get("pcursor"):
            return success(comments(1, 21), "page-2")
        return httpx.Response(501)

    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        client = LiveCommentClient(auth_provider=provider, client=http_client)
        with pytest.raises(CommentCollectionInterrupted) as raised:
            client.fetch_root_comments(
                "photo", "user", None, on_progress=progress.append
            )

    saved = raised.value.progress
    assert saved.comments == comments(1, 21)
    assert saved.pcursor == "page-2"
    assert not saved.complete
    assert saved.llsid == provider.calls[0]["llsid"]
    assert len(provider.calls) == 4
    assert [call.get("pcursor", "") for call in provider.calls] == [
        "",
        "page-2",
        "page-2",
        "page-2",
    ]
    assert delays == [1.0, 1.0, 2.0]
    assert len(progress) == 1
    assert "HTTP 501" in str(raised.value)
    assert "https://" not in str(raised.value)
    assert "fresh-signature" not in str(raised.value)


def test_resume_keeps_llsid_deduplicates_overlap_and_stops_at_50(
    delays: list[float],
) -> None:
    provider = SigningProvider()
    resume = CommentCollectionProgress(
        "photo", "user", "original-list-session", "page-2", comments(1, 21)
    )
    progress: list[CommentCollectionProgress] = []

    def handler(request: httpx.Request) -> httpx.Response:
        fields = body_fields(request)
        assert fields["llsid"] == "original-list-session"
        if fields["pcursor"] == "page-2":
            return success(comments(16, 36), "page-3")
        assert fields["pcursor"] == "page-3"
        assert fields["count"] == "15"
        return success(comments(36, 51), "page-4")

    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        client = LiveCommentClient(auth_provider=provider, client=http_client)
        result = client.fetch_root_comments(
            "photo", "user", 50, resume=resume, on_progress=progress.append
        )

    assert result == comments(1, 51)
    assert len(provider.calls) == 2
    assert delays == [1.0]
    assert progress[-1].complete
    assert progress[-1].pcursor == "page-4"
    assert resume.comments == comments(1, 21)


@pytest.mark.parametrize("status", [400, 401, 403, 404])
def test_permanent_http_rejections_are_not_retried(
    status: int, delays: list[float]
) -> None:
    provider = SigningProvider()
    with httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(status))
    ) as http_client:
        client = LiveCommentClient(auth_provider=provider, client=http_client)
        with pytest.raises(CommentCollectionInterrupted) as raised:
            client.fetch_root_comments("photo", "user", None)
    assert len(provider.calls) == 1
    assert delays == []
    assert raised.value.progress.comments == []
    assert raised.value.progress.pcursor == ""


def test_api_result_rejection_is_not_retried_or_echoed(delays: list[float]) -> None:
    provider = SigningProvider()
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={"result": 8, "error_msg": "private-response-text"},
            )
        )
    ) as http_client:
        client = LiveCommentClient(auth_provider=provider, client=http_client)
        with pytest.raises(
            CommentCollectionInterrupted, match="A API mobile rejeitou"
        ) as raised:
            client.fetch_root_comments("photo", "user", None)
    assert len(provider.calls) == 1
    assert delays == []
    assert "private-response-text" not in str(raised.value)


def test_network_error_retries_same_page_without_duplicates(
    delays: list[float],
) -> None:
    provider = SigningProvider()

    def handler(request: httpx.Request) -> httpx.Response:
        if len(provider.calls) < 3:
            raise httpx.ReadTimeout("private-request-url", request=request)
        return success(comments(1, 3), "no_more")

    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        client = LiveCommentClient(auth_provider=provider, client=http_client)
        assert client.fetch_root_comments("photo", "user", None) == comments(1, 3)
    assert delays == [1.0, 2.0]
    assert len(provider.calls) == 3


def test_already_satisfied_limit_resumes_without_http(delays: list[float]) -> None:
    resume = CommentCollectionProgress(
        "photo", "user", "session", "page-2", comments(1, 21)
    )
    client = LiveCommentClient(auth_provider=None)
    try:
        assert client.fetch_root_comments(
            "photo", "user", 10, resume=resume
        ) == comments(1, 11)
    finally:
        client.client.close()
    assert delays == []


def test_resume_rejects_mismatched_post_without_http() -> None:
    resume = CommentCollectionProgress("other-photo", "user", "session", "page-2", [])
    client = LiveCommentClient(auth_provider=None)
    try:
        with pytest.raises(ValueError, match="outro post"):
            client.fetch_root_comments("photo", "user", None, resume=resume)
    finally:
        client.client.close()


def test_repeated_cursor_keeps_partial_incomplete(delays: list[float]) -> None:
    provider = SigningProvider()

    def handler(request: httpx.Request) -> httpx.Response:
        number = len(provider.calls)
        return success(comments(number, number + 1), "same-cursor")

    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        client = LiveCommentClient(auth_provider=provider, client=http_client)
        with pytest.raises(
            CommentCollectionInterrupted, match="repetiu um cursor"
        ) as raised:
            client.fetch_root_comments("photo", "user", None)
    assert raised.value.progress.comments == comments(1, 3)
    assert not raised.value.progress.complete
    assert len(provider.calls) == 2
    assert delays == [1.0]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_attempts": 0},
        {"max_attempts": True},
        {"backoff_base": -1},
        {"backoff_base": float("nan")},
        {"page_delay": -1},
        {"page_delay": float("inf")},
    ],
)
def test_invalid_retry_configuration_is_rejected(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        LiveCommentClient(**kwargs)  # type: ignore[arg-type]

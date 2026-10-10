from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest

from kwai_collector.clients.comment_collection_progress import (
    CommentCollectionInterrupted,
    CommentCollectionProgress,
)
from kwai_collector.clients.live_comment_client import LiveCommentClient
from kwai_collector.config import Settings
from kwai_collector.providers.comment_checkpoint import (
    load_comment_checkpoint,
    save_comment_checkpoint,
)
from kwai_collector.providers.mobile_comment_provider import MobileCommentProvider
from kwai_collector.security.signature_provider import PreparedMobileRequest


@pytest.fixture
def progress() -> CommentCollectionProgress:
    return CommentCollectionProgress(
        "123",
        "example",
        "list-session",
        "page-2",
        [{"commentId": "1", "content": "comentário público"}],
        False,
    )


def test_checkpoint_roundtrip_contains_only_progress_fields(
    tmp_path: Path, progress: CommentCollectionProgress
) -> None:
    path = tmp_path / "nested" / "progress.json"
    save_comment_checkpoint(progress, path)
    assert load_comment_checkpoint(path) == progress
    data = json.loads(path.read_text(encoding="utf-8"))
    assert set(data) == {
        "version",
        "photo_id",
        "user_id",
        "llsid",
        "pcursor",
        "comments",
        "complete",
    }
    assert data["version"] == 1
    assert list(path.parent.iterdir()) == [path]


def test_failed_replace_preserves_original_and_removes_temporary_file(
    tmp_path: Path,
    progress: CommentCollectionProgress,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "progress.json"
    save_comment_checkpoint(progress, path)
    original = path.read_bytes()

    def fail_replace(source: Path, destination: Path) -> None:
        assert source.parent == destination.parent
        raise PermissionError("private-details")

    monkeypatch.setattr(
        "kwai_collector.providers.comment_checkpoint.os.replace", fail_replace
    )
    with pytest.raises(ValueError) as raised:
        save_comment_checkpoint(
            CommentCollectionProgress("123", "example", "session", "page-3", []), path
        )
    assert path.read_bytes() == original
    assert list(tmp_path.iterdir()) == [path]
    assert "private-details" not in str(raised.value)


@pytest.mark.parametrize(
    "change",
    [
        {"version": 2},
        {"version": True},
        {"photo_id": ""},
        {"user_id": None},
        {"llsid": "   "},
        {"pcursor": None},
        {"comments": ["bad-comment"]},
        {"complete": "false"},
        {"token": "private-token"},
    ],
)
def test_checkpoint_rejects_invalid_schema_without_echoing_values(
    tmp_path: Path, progress: CommentCollectionProgress, change: dict[str, Any]
) -> None:
    path = tmp_path / "progress.json"
    save_comment_checkpoint(progress, path)
    data = json.loads(path.read_text(encoding="utf-8"))
    data.update(change)
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError) as raised:
        load_comment_checkpoint(path)
    assert "private-token" not in str(raised.value)


def test_checkpoint_missing_and_invalid_json_have_safe_errors(tmp_path: Path) -> None:
    path = tmp_path / "progress.json"
    with pytest.raises(ValueError, match="Não existe progresso"):
        load_comment_checkpoint(path)
    path.write_text("{private-invalid-json", encoding="utf-8")
    with pytest.raises(ValueError, match="JSON válido") as raised:
        load_comment_checkpoint(path)
    assert "private-invalid-json" not in str(raised.value)


class AuthProvider:
    def prepare(
        self,
        *,
        query: dict[str, str],
        body: dict[str, str],
        headers: dict[str, str],
    ) -> PreparedMobileRequest:
        return PreparedMobileRequest(query=query, body=body, headers=headers)


def test_provider_saves_partial_checkpoint_and_resumes_to_normalized_comments(
    tmp_path: Path,
) -> None:
    provider = MobileCommentProvider(auth_provider=AuthProvider())
    provider.checkpoint_path = tmp_path / "progress.json"
    requests: list[dict[str, str]] = []
    fail_second_page = True

    def handler(request: httpx.Request) -> httpx.Response:
        fields = {
            key: value[-1] for key, value in parse_qs(request.content.decode()).items()
        }
        requests.append(fields)
        if fields.get("pcursor") == "page-2":
            if fail_second_page:
                return httpx.Response(501)
            return httpx.Response(
                200,
                json={
                    "result": 1,
                    "pcursor": "no_more",
                    "rootComments": [{"commentId": "2", "content": "second"}],
                },
            )
        return httpx.Response(
            200,
            json={
                "result": 1,
                "pcursor": "page-2",
                "rootComments": [{"commentId": "1", "content": "first"}],
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        provider.live_client = LiveCommentClient(
            auth_provider=provider.auth_provider,
            client=http_client,
            backoff_base=0,
            page_delay=0,
        )
        with pytest.raises(CommentCollectionInterrupted):
            provider.get_comments("https://www.kwai.com/@example/video/123", None)
        saved = load_comment_checkpoint(provider.checkpoint_path)
        assert saved.pcursor == "page-2"
        assert len(saved.comments) == 1
        assert not saved.complete
        fail_second_page = False
        provider.resume_collection = True
        result = provider.get_comments("https://www.kwai.com/@example/video/123", None)
    assert [comment.id for comment in result] == ["1", "2"]
    assert requests[-1]["pcursor"] == "page-2"
    assert requests[-1]["llsid"] == saved.llsid
    assert load_comment_checkpoint(provider.checkpoint_path).complete


def test_provider_passes_retry_settings_to_new_live_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, Any] = {}

    class FakeLiveClient:
        def __init__(self, **kwargs: Any) -> None:
            observed.update(kwargs)

        def fetch_root_comments(self, **kwargs: Any) -> list[dict[str, Any]]:
            return []

    monkeypatch.setattr(
        "kwai_collector.providers.mobile_comment_provider.LiveCommentClient",
        FakeLiveClient,
    )
    provider = MobileCommentProvider(auth_provider=AuthProvider())
    provider.max_attempts = 5
    provider.backoff_base = 2.5
    provider.page_delay = 1.75
    assert provider.get_comments("https://www.kwai.com/@example/video/123", None) == []
    assert observed["max_attempts"] == 5
    assert observed["backoff_base"] == 2.5
    assert observed["page_delay"] == 1.75


def test_page_delay_setting_defaults_to_two_and_rejects_negative() -> None:
    assert Settings(_env_file=None).mobile_page_delay == 2.0
    with pytest.raises(ValueError):
        Settings(_env_file=None, mobile_page_delay=-1)


@pytest.mark.parametrize("post", ["https://www.kwai.com/@example/video/123", "123"])
def test_provider_resumes_saved_numeric_author_from_handle_url_or_photo_id(
    tmp_path: Path, post: str
) -> None:
    path = tmp_path / "progress.json"
    saved = CommentCollectionProgress(
        "123",
        "456",
        "original-session",
        "page-2",
        [{"commentId": "1", "content": "first"}],
    )
    save_comment_checkpoint(saved, path)
    provider = MobileCommentProvider(auth_provider=AuthProvider())
    provider.checkpoint_path = path
    provider.resume_collection = True
    received: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        fields = {
            key: value[-1] for key, value in parse_qs(request.content.decode()).items()
        }
        received.append(fields)
        assert fields["user_id"] == "456"
        assert fields["pcursor"] == "page-2"
        assert fields["llsid"] == "original-session"
        return httpx.Response(
            200,
            json={
                "result": 1,
                "pcursor": "no_more",
                "rootComments": [{"commentId": "2", "content": "second"}],
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        provider.live_client = LiveCommentClient(
            auth_provider=provider.auth_provider,
            client=http_client,
            page_delay=0,
        )
        result = provider.get_comments(post, None)
    assert [comment.id for comment in result] == ["1", "2"]
    assert len(received) == 1
    assert load_comment_checkpoint(path).user_id == "456"


@pytest.mark.parametrize(
    ("post", "user_id"),
    [
        ("https://www.kwai.com/@example/video/123", "999"),
        ("https://www.kwai.com/@example/video/999", None),
    ],
)
def test_provider_rejects_explicit_author_or_photo_mismatch_without_http(
    tmp_path: Path, post: str, user_id: str | None
) -> None:
    path = tmp_path / "progress.json"
    save_comment_checkpoint(
        CommentCollectionProgress("123", "456", "session", "page-2", []), path
    )
    original = path.read_bytes()
    provider = MobileCommentProvider(auth_provider=AuthProvider())
    provider.checkpoint_path = path
    provider.resume_collection = True

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("A mismatch must not send an HTTP request.")

    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        provider.live_client = LiveCommentClient(
            auth_provider=provider.auth_provider,
            client=http_client,
            page_delay=0,
        )
        with pytest.raises(ValueError, match="outro post ou autor"):
            provider.get_comments(post, None, user_id=user_id)
    assert path.read_bytes() == original

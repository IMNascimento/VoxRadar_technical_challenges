from __future__ import annotations

from urllib.parse import parse_qs

import httpx
import pytest

from kwai_collector.clients.live_comment_client import LiveCommentClient
from kwai_collector.security.comment_list_v2_request_provider import (
    CommentListV2RequestProvider,
    CommentListV2Signatures,
)
from kwai_collector.security.mobile_request_provider_factory import (
    criar_mobile_request_provider,
)


class RecordingSigner:
    def __init__(self) -> None:
        self.calls: list[
            tuple[
                dict[str, str],
                dict[str, str],
                str | None,
            ]
        ] = []

    def sign(
        self,
        *,
        query: dict[str, str],
        body: dict[str, str],
        client_salt: str | None,
    ) -> CommentListV2Signatures:
        self.calls.append(
            (
                dict(query),
                dict(body),
                client_salt,
            )
        )

        page = body.get("pcursor") or "first"

        return CommentListV2Signatures(
            sig=f"sig-{page}",
            sig3=f"sig3-{page}",
            tokensig=f"token-{page}",
        )


def test_each_page_is_signed_after_cleaning_old_fields() -> None:
    signer = RecordingSigner()

    provider = CommentListV2RequestProvider(
        signer=signer,
        query_fields={
            "shared": "query",
            "__NS_sig3": "configured-old",
        },
        body_fields={
            "shared": "body",
            "__NStokensig": "configured-old",
            "client_salt": "body-salt",
        },
        header_fields={
            "X-Test": "configured",
        },
    )

    query = {
        "llsid": "same",
        "client_salt": "query-salt",
        "sig": "old-query",
        "__NStokensig": "old-query",
    }

    body = {
        "llsid": "same",
        "photoId": "123",
        "sig": "old-body",
        "__NS_sig3": "old-body",
    }

    headers = {
        "Accept": "application/json",
    }

    first = provider.prepare(
        query=query,
        body=body,
        headers=headers,
    )

    second = provider.prepare(
        query=query,
        body={
            **body,
            "pcursor": "next",
        },
        headers=headers,
    )

    assert [call[1].get("pcursor") for call in signer.calls] == [
        None,
        "next",
    ]

    for (
        unsigned_query,
        unsigned_body,
        salt,
    ) in signer.calls:
        assert salt == "query-salt"

        assert "llsid" not in unsigned_query

        assert unsigned_body["llsid"] == "same"

        assert "shared" not in unsigned_query

        assert unsigned_body["shared"] == "body"

        assert unsigned_body["client_salt"] == "body-salt"

        for field in (
            "sig",
            "__NS_sig3",
            "__NStokensig",
        ):
            assert field not in unsigned_query

            assert field not in unsigned_body

        assert "client_salt" not in unsigned_query

    assert first.body["sig"] == "sig-first"

    assert second.body["sig"] == "sig-next"

    assert first.query["__NS_sig3"] == "sig3-first"

    assert second.query["__NS_sig3"] == "sig3-next"

    assert first.body["__NStokensig"] == "token-first"

    assert second.body["__NStokensig"] == "token-next"

    assert "sig" not in first.query

    assert "__NS_sig3" not in first.body

    assert "__NStokensig" not in first.query

    assert "llsid" not in first.query

    assert first.body["client_salt"] == "body-salt"

    assert first.headers == {
        "Accept": "application/json",
        "X-Test": "configured",
    }

    assert query["sig"] == "old-query"

    assert body["sig"] == "old-body"

    assert headers == {
        "Accept": "application/json",
    }


@pytest.mark.parametrize(
    (
        "signatures",
        "field",
    ),
    [
        (
            CommentListV2Signatures(
                sig="",
                sig3="valid",
            ),
            "sig",
        ),
        (
            CommentListV2Signatures(
                sig="valid",
                sig3=" ",
            ),
            "__NS_sig3",
        ),
        (
            CommentListV2Signatures(
                sig="valid",
                sig3="valid",
                tokensig="",
            ),
            "__NStokensig",
        ),
    ],
)
def test_rejects_empty_signatures(
    signatures: CommentListV2Signatures,
    field: str,
) -> None:
    class FixedSigner:
        def sign(
            self,
            *,
            query: dict[str, str],
            body: dict[str, str],
            client_salt: str | None,
        ) -> CommentListV2Signatures:
            return signatures

    provider = CommentListV2RequestProvider(
        signer=FixedSigner(),
    )

    with pytest.raises(
        ValueError,
        match=field,
    ):
        provider.prepare(
            query={},
            body={
                "photoId": "123",
            },
            headers={},
        )


def test_omits_stale_tokensig_when_signer_does_not_return_one() -> None:
    class SignerWithoutToken:
        def sign(
            self,
            *,
            query: dict[str, str],
            body: dict[str, str],
            client_salt: str | None,
        ) -> CommentListV2Signatures:
            return CommentListV2Signatures(
                sig="fresh-sig",
                sig3="fresh-sig3",
            )

    provider = CommentListV2RequestProvider(
        signer=SignerWithoutToken(),
    )

    prepared = provider.prepare(
        query={
            "__NStokensig": "old-query",
        },
        body={
            "photoId": "123",
            "__NStokensig": "old-body",
        },
        headers={},
    )

    assert "__NStokensig" not in prepared.query

    assert "__NStokensig" not in prepared.body


def test_requires_tokensig_when_client_salt_is_present() -> None:
    class SignerWithoutToken:
        def sign(
            self,
            *,
            query: dict[str, str],
            body: dict[str, str],
            client_salt: str | None,
        ) -> CommentListV2Signatures:
            assert client_salt == "salt"

            return CommentListV2Signatures(
                sig="fresh-sig",
                sig3="fresh-sig3",
            )

    provider = CommentListV2RequestProvider(
        signer=SignerWithoutToken(),
    )

    with pytest.raises(
        ValueError,
        match="__NStokensig",
    ):
        provider.prepare(
            query={
                "client_salt": "salt",
            },
            body={
                "photoId": "123",
            },
            headers={},
        )


def test_live_client_posts_a_fresh_pair_for_each_cursor() -> None:
    signer = RecordingSigner()

    provider = CommentListV2RequestProvider(
        signer=signer,
    )

    sent: list[
        tuple[
            dict[str, str],
            dict[str, str],
        ]
    ] = []

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        query = dict(request.url.params)

        body = {
            key: values[-1]
            for key, values in parse_qs(
                request.content.decode(),
                keep_blank_values=True,
            ).items()
        }

        sent.append(
            (
                query,
                body,
            )
        )

        if "pcursor" not in body:
            return httpx.Response(
                200,
                json={
                    "result": 1,
                    "pcursor": "next",
                    "rootComments": [
                        {
                            "id": str(index),
                        }
                        for index in range(20)
                    ],
                },
            )

        return httpx.Response(
            200,
            json={
                "result": 1,
                "pcursor": "no_more",
                "rootComments": [
                    {
                        "id": str(index),
                    }
                    for index in range(
                        20,
                        25,
                    )
                ],
            },
        )

    transport = httpx.MockTransport(handler)

    with httpx.Client(transport=transport) as http_client:
        client = LiveCommentClient(
            auth_provider=provider,
            client=http_client,
        )

        comments = client.fetch_root_comments(
            "123",
            "user",
            25,
        )

    assert len(comments) == 25

    assert len(sent) == len(signer.calls) == 2

    assert [body.get("pcursor") for _, body in sent] == [
        None,
        "next",
    ]

    for index, (
        query,
        body,
    ) in enumerate(sent):
        page = "first" if index == 0 else "next"

        assert body["sig"] == f"sig-{page}"

        assert query["__NS_sig3"] == f"sig3-{page}"

        assert body["__NStokensig"] == f"token-{page}"

        assert "llsid" not in query
        assert "llsid" in body
        assert "sig" not in query

        assert "__NS_sig3" not in body


def test_factory_can_wrap_an_injected_provider_in_android_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from kwai_collector.security.android_request_profile import (
        AndroidRequestProfile,
    )

    timestamps = iter(
        (
            "100",
            "200",
        )
    )

    monkeypatch.setattr(
        AndroidRequestProfile,
        "_timestamp_ms",
        staticmethod(lambda: next(timestamps)),
    )

    signer = RecordingSigner()

    endpoint_provider = CommentListV2RequestProvider(
        signer=signer,
        query_fields={
            "session": "test-session",
            "timestamp": "stale",
        },
        body_fields={
            "os": "android",
            "client_key": "test-client",
        },
    )

    provider = criar_mobile_request_provider(
        delegate=endpoint_provider,
    )

    first = provider.prepare(
        query={
            "llsid": "123",
        },
        body={
            "photoId": "1",
        },
        headers={},
    )

    second = provider.prepare(
        query={
            "llsid": "123",
        },
        body={
            "photoId": "1",
            "pcursor": "next",
        },
        headers={},
    )

    assert first.query["session"] == second.query["session"] == "test-session"

    assert [
        first.query["timestamp"],
        second.query["timestamp"],
    ] == [
        "100",
        "200",
    ]

    assert [call[0]["timestamp"] for call in signer.calls] == [
        "100",
        "200",
    ]

    assert first.body["os"] == second.body["os"] == "android"

    assert first.body["client_key"] == second.body["client_key"] == "test-client"

    assert first.query["__NS_sig3"] == "sig3-first"

    assert second.query["__NS_sig3"] == "sig3-next"

    assert first.body["sig"] == "sig-first"

    assert second.body["sig"] == "sig-next"

    assert len(signer.calls) == 2


def test_factory_rejects_delegate_with_another_auth_source() -> None:
    endpoint_provider = CommentListV2RequestProvider(
        signer=RecordingSigner(),
    )

    with pytest.raises(
        ValueError,
        match="delegate",
    ):
        criar_mobile_request_provider(
            delegate=endpoint_provider,
            auth_endpoint=("http://localhost:1234/sign"),
        )

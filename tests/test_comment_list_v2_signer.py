import hashlib
import json
from pathlib import Path

import pytest

from kwai_collector.security.comment_list_v2_request_provider import (
    CommentListV2RequestProvider,
)
from kwai_collector.security.comment_list_v2_signer import (
    COMMENT_LIST_V2_PATH,
    KwaiLite103CommentListV2Signer,
    calculate_v10_tokensig,
)
from kwai_collector.security.native_signature_service import NativeSignatureService
from kwai_collector.security.native_signer import (
    NativeSignerUnavailableError,
    UnavailableNativeSigner,
)


class RecordingSig3Signer:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, str], dict[str, str]]] = []

    def sign(
        self,
        *,
        method: str,
        path: str,
        query: dict[str, str],
        body: dict[str, str],
    ) -> str:
        self.calls.append((method, path, dict(query), dict(body)))
        return f"sig3-{body.get('pcursor', 'first')}"


def _native_vector_signatures() -> dict[str, str]:
    path = Path(__file__).parent / "fixtures" / "native_getclock_vectors.json"
    vectors = json.loads(path.read_text(encoding="utf-8"))["vectors"]
    return {vector["name"]: vector["sig"] for vector in vectors}


def test_each_cursor_is_signed_then_passed_to_sig3_with_tokensig() -> None:
    sig3 = RecordingSig3Signer()
    provider = CommentListV2RequestProvider(
        signer=KwaiLite103CommentListV2Signer(sig3_signer=sig3),
        query_fields={"llsid": "123", "app": "1"},
        body_fields={"count": "20", "user_id": "789", "client_salt": "salt"},
    )
    vectors = _native_vector_signatures()

    first = provider.prepare(query={}, body={"photoId": "456"}, headers={})
    second = provider.prepare(
        query={}, body={"photoId": "456", "pcursor": "next"}, headers={}
    )

    for request, name, cursor in (
        (first, "synthetic_first_page", None),
        (second, "synthetic_cursor", "next"),
    ):
        assert request.body["sig"] == vectors[name]
        assert (
            request.body["__NStokensig"]
            == hashlib.sha256((vectors[name] + "salt").encode("utf-8")).hexdigest()
        )
        assert "client_salt" not in request.body
        assert "client_salt" not in request.query
        assert request.body.get("pcursor") == cursor

    assert first.query["__NS_sig3"] == "sig3-first"
    assert second.query["__NS_sig3"] == "sig3-next"
    for (_, _, query, body), request in zip(sig3.calls, (first, second), strict=True):
        assert query == {"llsid": "123", "app": "1"}
        assert body == request.body
        assert "__NS_sig3" not in body
    assert [(method, path) for method, path, _, _ in sig3.calls] == [
        ("POST", COMMENT_LIST_V2_PATH),
        ("POST", COMMENT_LIST_V2_PATH),
    ]


def test_empty_client_salt_omits_tokensig() -> None:
    sig3 = RecordingSig3Signer()
    signer = KwaiLite103CommentListV2Signer(sig3_signer=sig3)
    result = signer.sign(query={"app": "1"}, body={"photoId": "456"}, client_salt=None)

    assert result.tokensig is None
    assert "__NStokensig" not in sig3.calls[0][3]
    assert calculate_v10_tokensig("sig", "") is None


def test_explicit_native_service_is_preserved_when_falsey() -> None:
    class FalseyNativeSignatureService(NativeSignatureService):
        def __bool__(self) -> bool:
            return False

    sig3 = RecordingSig3Signer()
    signer = KwaiLite103CommentListV2Signer(
        sig3_signer=sig3,
        native_signature_service=FalseyNativeSignatureService(
            UnavailableNativeSigner()
        ),
    )

    with pytest.raises(NativeSignerUnavailableError):
        signer.sign(query={"app": "1"}, body={"photoId": "456"}, client_salt=None)

    assert sig3.calls == []

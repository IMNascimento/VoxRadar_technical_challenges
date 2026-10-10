import pytest

from kwai_collector.security.native_signature_service import (
    NativeSignatureService,
)
from kwai_collector.security.native_signer import (
    NativeSignerUnavailableError,
    UnavailableNativeSigner,
)


class FakeNativeSigner:
    def __init__(self) -> None:
        self.received: bytes | None = None

    def sign(
        self,
        canonical_bytes: bytes,
    ) -> str:
        self.received = canonical_bytes
        return "fake-signature"


def test_service_envia_bytes_canonicalizados_para_signer():
    signer = FakeNativeSigner()

    service = NativeSignatureService(
        signer=signer,
    )

    resultado = service.sign_request(
        query={
            "z": "3",
        },
        body={
            "a": "1",
        },
    )

    assert signer.received == (b"a=1z=3")

    assert resultado.signature == ("fake-signature")

    assert resultado.input.canonical_text == ("a=1z=3")


def test_service_preserva_client_salt_na_entrada():
    signer = FakeNativeSigner()

    service = NativeSignatureService(
        signer=signer,
    )

    resultado = service.sign_request(
        query={
            "client_salt": "abc",
            "photo_id": "123",
        },
        body={},
    )

    assert resultado.input.params == {
        "client_salt": "abc",
        "photo_id": "123",
    }

    assert signer.received == (b"client_salt=abcphoto_id=123")


def test_unavailable_signer_falha_explicitamente():
    service = NativeSignatureService(
        signer=UnavailableNativeSigner(),
    )

    with pytest.raises(
        NativeSignerUnavailableError,
    ):
        service.sign_request(
            query={
                "photo_id": "123",
            },
            body={},
        )

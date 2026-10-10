import json
from pathlib import Path

import pytest

from kwai_collector.security.kwai_lite_103_offline_signer import (
    KwaiLite103OfflineSigner,
)
from kwai_collector.security.native_signature_service import (
    NativeSignatureService,
)

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "native_getclock_vectors.json"
_VECTORS = {
    vector["name"]: vector
    for vector in json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))["vectors"]
}


@pytest.mark.parametrize("name", list(_VECTORS))
def test_signer_reproduces_native_synthetic_vectors(name: str) -> None:
    vector = _VECTORS[name]
    signer = KwaiLite103OfflineSigner()

    assert signer.sign(bytes.fromhex(vector["input_hex"])) == vector["sig"]


@pytest.mark.parametrize(
    ("cursor", "vector_name"),
    [(None, "synthetic_first_page"), ("next", "synthetic_cursor")],
)
def test_service_signs_first_and_cursor_pages(
    cursor: str | None,
    vector_name: str,
) -> None:
    query: dict[str, object] = {"llsid": "123", "app": 1}
    if cursor is not None:
        query["pcursor"] = cursor

    result = NativeSignatureService(
        signer=KwaiLite103OfflineSigner(),
    ).sign_request(
        query=query,
        body={"count": 20, "photoId": "456", "user_id": "789"},
    )

    assert result.input.canonical_bytes.hex() == _VECTORS[vector_name]["input_hex"]
    assert result.signature == _VECTORS[vector_name]["sig"]


def test_signer_rejects_other_versions_and_packages() -> None:
    with pytest.raises(ValueError, match="só foi validado"):
        KwaiLite103OfflineSigner(app_version="13.8.30.646620")

    with pytest.raises(ValueError, match="só foi validado"):
        KwaiLite103OfflineSigner(app_package="com.kwai.video")

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from kwai_collector.security.comment_list_v2_sig3_record import (
    encode_comment_list_v2_sig3_record,
)
from kwai_collector.security.comment_list_v2_sig3_wrapper import Sig3Nonce
from kwai_collector.security.kwai_lite_103_offline_sig3_signer import (
    KwaiLite103OfflineSig3Signer,
    _encrypt_digest,
    _load_material,
    calculate_kwai_lite_103_sig3_crc,
)

_FIXTURE = Path(__file__).parent / "fixtures/native_sig3_vectors.json"
_VECTORS = json.loads(_FIXTURE.read_text(encoding="utf-8"))["vectors"]
_MODULE = "kwai_collector.security.kwai_lite_103_offline_sig3_signer"


@pytest.mark.parametrize("vector", _VECTORS, ids=[v["name"] for v in _VECTORS])
def test_offline_calculation_matches_original_native_library(vector: dict) -> None:
    _, rounds, final = _load_material()
    assert (
        _encrypt_digest(bytes.fromhex(vector["hmac_sha256"]), rounds, final).hex()
        == (vector["ciphertext"])
    )
    crc = calculate_kwai_lite_103_sig3_crc(vector["raw_input"])
    assert crc == int(vector["crc32"], 16)
    assert (
        encode_comment_list_v2_sig3_record(
            header=vector["header"],
            context_id=vector["context_id"],
            counter=vector["counter"],
            request_crc=crc,
            timestamp_seconds=vector["timestamp_seconds"],
            flags=bytes.fromhex(vector["flags"]),
        )
        == vector["native_hex"]
    )


def test_complete_signer_matches_native_record_and_nonce_wrapper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vector = _VECTORS[0]
    nonce = Sig3Nonce.from_words(123456, 0x13572468)
    monkeypatch.setattr(Sig3Nonce, "generate", classmethod(lambda cls: nonce))
    monkeypatch.setattr(
        f"{_MODULE}.time.time_ns", lambda: vector["timestamp_seconds"] * 1_000_000_000
    )
    signer = KwaiLite103OfflineSig3Signer(context_id=vector["context_id"])

    signed = signer.sign(
        method="POST", path="/rest/o/comment/list/v2", query={"a": "1"}, body={}
    )

    assert base64.urlsafe_b64decode(signed + "=") == (
        nonce.prefix + vector["native_hex"].encode("ascii")
    )


@pytest.mark.parametrize("text", ["", " \t\r\n"])
def test_empty_native_input_is_rejected(text: str) -> None:
    with pytest.raises(ValueError, match="vazio"):
        calculate_kwai_lite_103_sig3_crc(text)


@pytest.mark.parametrize(
    ("method", "path", "query"),
    [
        ("GET", "/rest/o/comment/list/v2", {}),
        ("POST", "/rest/o/comment/sublist", {}),
        ("POST", "/rest/o/comment/list/v2", {"appver": "13.8.30.646620"}),
        ("POST", "/rest/o/comment/list/v2", {"pkg": "com.kwai.video"}),
    ],
)
def test_signer_rejects_unvalidated_routes_and_versions(
    method: str, path: str, query: dict[str, str]
) -> None:
    with pytest.raises(ValueError):
        KwaiLite103OfflineSig3Signer().sign(
            method=method, path=path, query=query, body={}
        )

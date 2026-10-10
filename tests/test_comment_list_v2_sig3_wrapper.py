from __future__ import annotations

import base64

import pytest

from kwai_collector.security.comment_list_v2_sig3_wrapper import (
    Sig3Nonce,
    encode_comment_list_v2_sig3,
)


@pytest.mark.parametrize(
    ("minute", "random_word", "decimal", "prefix_hex"),
    [
        (123456, 0x13572468, "1393622638789780032", "135724680001e240"),
        (123456, -1, "-4294843840", "ffffffff0001e240"),
        (123456, -(1 << 31), "-9223372036854652352", "800000000001e240"),
    ],
)
def test_nonce_matches_real_java_rw_i(
    minute: int, random_word: int, decimal: str, prefix_hex: str
) -> None:
    nonce = Sig3Nonce.from_words(minute, random_word)
    assert nonce.decimal == decimal
    assert nonce.prefix.hex() == prefix_hex


def test_sig3_wrapper_prepends_nonce_and_encodes_without_padding() -> None:
    nonce = Sig3Nonce.from_words(123456, 0x13572468)
    native_hex = "ab" * 24

    result = encode_comment_list_v2_sig3(nonce, native_hex)

    assert len(result) == 75
    assert "=" not in result
    assert base64.urlsafe_b64decode(result + "=") == nonce.prefix + native_hex.encode()


def test_generate_uses_current_minute_and_fresh_random_word(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "kwai_collector.security.comment_list_v2_sig3_wrapper.time.time_ns",
        lambda: 123456 * 60_000_000_000 + 59_000_000_000,
    )
    words = iter((0x13572468, 0x13572469))
    monkeypatch.setattr(
        "kwai_collector.security.comment_list_v2_sig3_wrapper.secrets.randbits",
        lambda bits: next(words),
    )

    first = Sig3Nonce.generate()
    second = Sig3Nonce.generate()

    assert first == Sig3Nonce.from_words(123456, 0x13572468)
    assert second == Sig3Nonce.from_words(123456, 0x13572469)
    assert first != second


@pytest.mark.parametrize("native_hex", ["a" * 47, "g" * 48, "á" * 48])
def test_sig3_wrapper_rejects_unexpected_native_result(native_hex: str) -> None:
    with pytest.raises(ValueError, match="48 ASCII hex"):
        encode_comment_list_v2_sig3(Sig3Nonce.from_words(1, 2), native_hex)

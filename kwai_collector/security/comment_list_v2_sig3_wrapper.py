"""Nonce and output encoding for Kwai Lite 10.3 comment-list ``__NS_sig3``.

The app passes the nonce's signed decimal value into ``KSecurity.atlasSign``.
After signing, it prepends the same nonce as eight big-endian bytes and
URL-safe-base64 encodes the result without padding. The native signature
calculation itself is intentionally outside this module.

A1_Radar.
"""

from __future__ import annotations

import base64
import secrets
import time
from dataclasses import dataclass

_INT32_MIN = -(1 << 31)
_INT32_MAX = (1 << 31) - 1
_INT64_MAX = (1 << 63) - 1
_UINT64_MASK = (1 << 64) - 1


@dataclass(frozen=True, slots=True)
class Sig3Nonce:
    """The signed Java long created by ``rw/i`` for one signing call."""

    value: int

    @classmethod
    def from_words(cls, minute: int, random_word: int) -> Sig3Nonce:
        """Match ``((long) random_word << 32) | (long) minute``."""
        if not _INT32_MIN <= minute <= _INT32_MAX:
            raise ValueError("minute must fit in a signed Java int")
        if not _INT32_MIN <= random_word <= _INT32_MAX:
            raise ValueError("random_word must fit in a signed Java int")

        unsigned = ((random_word << 32) | minute) & _UINT64_MASK
        signed = unsigned if unsigned <= _INT64_MAX else unsigned - (1 << 64)
        return cls(signed)

    @classmethod
    def generate(cls) -> Sig3Nonce:
        """Create fresh nonce words using the app's current-minute format."""
        minute = time.time_ns() // 60_000_000_000
        minute &= (1 << 32) - 1
        if minute > _INT32_MAX:
            minute -= 1 << 32

        random_word = secrets.randbits(32)
        if random_word > _INT32_MAX:
            random_word -= 1 << 32
        return cls.from_words(minute, random_word)

    @property
    def decimal(self) -> str:
        return str(self.value)

    @property
    def prefix(self) -> bytes:
        return (self.value & _UINT64_MASK).to_bytes(8, "big")


def encode_comment_list_v2_sig3(nonce: Sig3Nonce, native_hex: str) -> str:
    """Wrap the 48-character native result as the app does in ``cd1/b.c``."""
    if len(native_hex) != 48 or any(
        char not in "0123456789abcdefABCDEF" for char in native_hex
    ):
        raise ValueError("native sig3 result must be 48 ASCII hex characters")
    return (
        base64.urlsafe_b64encode(nonce.prefix + native_hex.encode("ascii"))
        .rstrip(b"=")
        .decode("ascii")
    )

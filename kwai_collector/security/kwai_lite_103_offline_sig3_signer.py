"""Kwai Lite 10.3.20.540101 comment sig3 without Android.

The v10 default native route uses HMAC-SHA256, the APK's fixed encryption
tables, and CRC32. Its 24-byte record includes a process identifier, a call
counter, and the current time. The request wrapper adds a fresh nonce.

A1_Radar.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import struct
import threading
import time
import zlib
from functools import cache
from importlib.resources import files

from kwai_collector.security.comment_list_v2_sig3_canonical import (
    COMMENT_LIST_V2_PATH,
    canonicalize_comment_list_v2_sig3,
)
from kwai_collector.security.comment_list_v2_sig3_record import (
    encode_comment_list_v2_sig3_record,
)
from kwai_collector.security.comment_list_v2_sig3_wrapper import (
    Sig3Nonce,
    encode_comment_list_v2_sig3,
)
from kwai_collector.security.kwai_lite_103_offline_signer import (
    KwaiLite103OfflineSigner,
)

_MATERIAL_FILE = "kwai_lite_103_sig3_material.bin"
_MATERIAL_SHA256 = "2194294f914ef583414ce81a6ac036c034e7c7b441e5685a5ffe9bc219165d3c"
_ROWS = (0, 5, 10, 15, 4, 9, 14, 3, 8, 13, 2, 7, 12, 1, 6, 11)
_JAVA_TRIM = "".join(chr(value) for value in range(33))


def _jni_modified_utf8(value: str) -> bytes:
    """Match the JNI GetStringUTFChars encoding used by the native dispatcher."""
    units = value.encode("utf-16-be", errors="surrogatepass")
    output = bytearray()
    for offset in range(0, len(units), 2):
        unit = (units[offset] << 8) | units[offset + 1]
        if 0 < unit < 0x80:
            output.append(unit)
        elif unit < 0x800:
            output.extend((0xC0 | (unit >> 6), 0x80 | (unit & 0x3F)))
        else:
            output.extend(
                (0xE0 | (unit >> 12), 0x80 | ((unit >> 6) & 0x3F), 0x80 | (unit & 0x3F))
            )
    return bytes(output)


@cache
def _load_material() -> tuple[bytes, tuple[int, ...], bytes]:
    """Load the fixed v10 APK tables bundled with the Python package."""
    material = files("kwai_collector.security").joinpath(_MATERIAL_FILE).read_bytes()
    if (
        len(material) != 151616
        or hashlib.sha256(material).hexdigest() != _MATERIAL_SHA256
    ):
        raise RuntimeError("As tabelas de assinatura Kwai Lite 10.3 estao invalidas.")
    return (
        material[:64],
        struct.unpack("<36864I", material[64:147520]),
        material[147520:],
    )


def _encrypt_digest(
    digest: bytes, round_tables: tuple[int, ...], final: bytes
) -> bytes:
    # Native command 0x28b2 encrypts a 32-byte digest with PKCS#7 padding.
    padded = digest + b"\x10" * 16
    encrypted = bytearray()
    for offset in range(0, 48, 16):
        state = padded[offset : offset + 16]
        for round_index in range(9):
            state = bytes(state[position] for position in _ROWS)
            output = bytearray(16)
            for column in range(4):
                start = column * 4
                combined = 0
                for position in range(start, start + 4):
                    combined ^= round_tables[
                        round_index * 4096 + position * 256 + state[position]
                    ]
                output[start : start + 4] = combined.to_bytes(4, "big")
            state = bytes(output)
        state = bytes(state[position] for position in _ROWS)
        encrypted.extend(
            final[position * 256 + value] for position, value in enumerate(state)
        )
    return bytes(encrypted)


def calculate_kwai_lite_103_sig3_crc(canonical_text: str) -> int:
    """Reproduce the request CRC passed into the native v10 sig3 record."""
    if not isinstance(canonical_text, str):
        raise TypeError("canonical_text deve ser str.")
    canonical_bytes = _jni_modified_utf8(canonical_text.strip(_JAVA_TRIM))
    if not canonical_bytes:
        raise ValueError("canonical_text nao pode ser vazio.")
    key, rounds, final = _load_material()
    digest = hmac.digest(key, canonical_bytes, "sha256")
    return zlib.crc32(_encrypt_digest(digest, rounds, final))


class KwaiLite103OfflineSig3Signer:
    """Implement the default v10 sig3 for comment list requests in Python."""

    APP_PACKAGE = KwaiLite103OfflineSigner.APP_PACKAGE
    APP_VERSION = KwaiLite103OfflineSigner.APP_VERSION

    def __init__(
        self,
        *,
        app_package: str = APP_PACKAGE,
        app_version: str = APP_VERSION,
        context_id: int | None = None,
    ) -> None:
        if app_package != self.APP_PACKAGE or app_version != self.APP_VERSION:
            raise ValueError(
                "Este assinador so foi validado para "
                f"{self.APP_PACKAGE} {self.APP_VERSION}."
            )
        if context_id is None:
            context_id = secrets.randbelow(1 << 31) + 1
        if type(context_id) is not int or not 1 <= context_id <= 1 << 31:
            raise ValueError("context_id deve estar entre 1 e 2147483648.")
        self._context_id = context_id
        self._counter = 0
        self._lock = threading.Lock()

    def sign(
        self,
        *,
        method: str,
        path: str,
        query: dict[str, str],
        body: dict[str, str],
    ) -> str:
        if method.upper() != "POST" or path != COMMENT_LIST_V2_PATH:
            raise ValueError(
                f"O assinador sig3 suporta somente POST {COMMENT_LIST_V2_PATH}."
            )
        for field, expected in (
            ("pkg", self.APP_PACKAGE),
            ("appver", self.APP_VERSION),
        ):
            actual = query.get(field) or body.get(field)
            if actual and actual != expected:
                raise ValueError(f"O assinador sig3 nao suporta {field}={actual}.")

        nonce = Sig3Nonce.generate()
        canonical = canonicalize_comment_list_v2_sig3(
            query=query, body=body, nonce=nonce.decimal
        )
        request_crc = calculate_kwai_lite_103_sig3_crc(canonical)
        with self._lock:
            self._counter = (self._counter + 1) & 0xFFFFFFFF
            counter = self._counter
        native_hex = encode_comment_list_v2_sig3_record(
            header=0x00165141,
            context_id=self._context_id,
            counter=counter,
            request_crc=request_crc,
            timestamp_seconds=(time.time_ns() // 1_000_000_000) & 0xFFFFFFFF,
            flags=b"\x00\x0d\x00",
        )
        return encode_comment_list_v2_sig3(nonce, native_hex)

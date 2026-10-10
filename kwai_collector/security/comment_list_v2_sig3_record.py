"""Encode the 24-byte record returned by Kwai Lite 10.3 native sig3.

The field values must come from the signing calculation and its process
context. This module implements only the final record encoding.

A1_Radar.
"""

from __future__ import annotations

import struct


def encode_comment_list_v2_sig3_record(
    *,
    header: int,
    context_id: int,
    counter: int,
    request_crc: int,
    timestamp_seconds: int,
    flags: bytes,
) -> str:
    """Pack native little-endian fields and apply the checksum/XOR transform."""
    words = (header, context_id, counter, request_crc, timestamp_seconds)
    if any(type(word) is not int or not 0 <= word <= 0xFFFFFFFF for word in words):
        raise ValueError("sig3 record fields must be unsigned 32-bit integers")
    if not isinstance(flags, bytes) or len(flags) != 3:
        raise ValueError("sig3 record flags must contain exactly three bytes")

    plain = struct.pack("<IIIII", *words) + flags
    checksum = (-sum(plain)) & 0xFF
    encoded = bytes(value ^ checksum ^ index for index, value in enumerate(plain))
    return (encoded + bytes([checksum])).hex()

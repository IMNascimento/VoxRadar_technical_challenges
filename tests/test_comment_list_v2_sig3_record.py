from __future__ import annotations

import pytest

from kwai_collector.security.comment_list_v2_sig3_record import (
    encode_comment_list_v2_sig3_record,
)


@pytest.mark.parametrize(
    ("counter", "timestamp_seconds", "expected"),
    [
        (1, 0x6AC65341, "1302465171f80d395b5b58597157c2990310862b464a4452"),
        (2, 0x6AC65343, "0e1f5b4c6ce51024454645446c4adf841c0d9b365b57594f"),
    ],
)
def test_record_matches_original_v10_library_vectors(
    counter: int, timestamp_seconds: int, expected: str
) -> None:
    assert (
        encode_comment_list_v2_sig3_record(
            header=0x00165141,
            context_id=0x6C59AF27,
            counter=counter,
            request_crc=0xC49E082F,
            timestamp_seconds=timestamp_seconds,
            flags=bytes.fromhex("000d00"),
        )
        == expected
    )

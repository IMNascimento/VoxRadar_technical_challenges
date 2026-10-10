from __future__ import annotations

import pytest

from kwai_collector.security.comment_list_v2_sig3_canonical import (
    canonicalize_comment_list_v2_sig3,
)


def test_preserves_query_and_body_pairs_and_excludes_double_underscore() -> None:
    query = {
        "z": "query",
        "same": "query",
        "empty": None,
        "sig": "native-sig",
        "__NS_sig3": "old",
    }
    body = {
        "same": "body",
        "z": None,
        "raw": "space + & = %",
        "_single": "kept",
        "__NStokensig": "excluded",
    }

    result = canonicalize_comment_list_v2_sig3(query=query, body=body, nonce="123")

    assert result == (
        "POST&/rest/o/comment/list/v2"
        "&_single=kept"
        "&empty="
        "&raw=space + & = %"
        "&same=body"
        "&same=query"
        "&sig=native-sig"
        "&z="
        "&z=query"
        "&123"
    )
    assert query["same"] == "query"
    assert body["same"] == "body"


def test_java_utf16_order_differs_from_python_code_point_order() -> None:
    result = canonicalize_comment_list_v2_sig3(
        query={"\ue000": "bmp", "\U00010000": "supplementary"},
        body=None,
    )

    assert result == (
        "POST&/rest/o/comment/list/v2&\U00010000=supplementary&\ue000=bmp"
    )


def test_empty_maps_only_have_method_and_path_until_nonce_is_added() -> None:
    assert canonicalize_comment_list_v2_sig3(query=None, body=None) == (
        "POST&/rest/o/comment/list/v2"
    )
    assert (
        canonicalize_comment_list_v2_sig3(query=None, body=None, nonce="987")
        == "POST&/rest/o/comment/list/v2&987"
    )


@pytest.mark.parametrize(
    ("query", "body"),
    [({1: "bad"}, {}), ({}, {"valid": 1})],
)
def test_rejects_non_string_map_entries(
    query: dict[object, object], body: dict[object, object]
) -> None:
    with pytest.raises(TypeError):
        canonicalize_comment_list_v2_sig3(query=query, body=body)  # type: ignore[arg-type]


def test_rejects_non_string_nonce() -> None:
    with pytest.raises(TypeError, match="nonce"):
        canonicalize_comment_list_v2_sig3(
            query={},
            body={},
            nonce=42,  # type: ignore[arg-type]
        )

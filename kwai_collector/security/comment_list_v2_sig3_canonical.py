"""Canonical input for the Kwai Lite 10.3 comment ``__NS_sig3``.

The installed app's ``cd1/b.a`` sorts query and form pairs together, appends
a per-call nonce, then passes the text to ``KSecurity.atlasSign``. This module
prepares that text; it does not implement ``atlasSign``.

A1_Radar.
"""

from __future__ import annotations

from collections.abc import Mapping

COMMENT_LIST_V2_PATH = "/rest/o/comment/list/v2"


def _java_string_order(value: str) -> bytes:
    """Match Java String.compareTo's unsigned UTF-16 code-unit ordering."""
    return value.encode("utf-16-be", errors="surrogatepass")


def canonicalize_comment_list_v2_sig3(
    *,
    query: Mapping[str, str | None] | None,
    body: Mapping[str, str | None] | None,
    nonce: str | None = None,
) -> str:
    """Sort full ``key=value`` pairs, retaining keys in both request parts.

    ``__*`` fields are excluded. ``nonce`` is the decimal value produced by
    ``rw/i`` for this signing call; omit it to inspect only the request prefix.
    """
    pairs: list[str] = []
    for source in (query, body):
        if source is None:
            continue
        for key, value in source.items():
            if not isinstance(key, str):
                raise TypeError("sig3 parameter keys must be strings")
            if value is not None and not isinstance(value, str):
                raise TypeError("sig3 parameter values must be strings or None")
            if not key.startswith("__"):
                pairs.append(f"{key}={value if value is not None else ''}")

    parts = [f"POST&{COMMENT_LIST_V2_PATH}", *sorted(pairs, key=_java_string_order)]
    if nonce is not None:
        if not isinstance(nonce, str):
            raise TypeError("sig3 nonce must be a string")
        parts.append(nonce)
    return "&".join(parts)

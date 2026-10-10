"""Prepare signed requests for the mobile root-comment list endpoint.

A1_Radar.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from kwai_collector.security.signature_provider import PreparedMobileRequest


@dataclass(frozen=True)
class CommentListV2Signatures:
    sig: str
    sig3: str
    tokensig: str | None = None


class CommentListV2Signer(Protocol):
    """Supply signatures for one complete, unsigned comment-list request."""

    def sign(
        self,
        *,
        query: dict[str, str],
        body: dict[str, str],
        client_salt: str | None,
    ) -> CommentListV2Signatures: ...


def _copy_fields(fields: Mapping[str, str] | None, *, name: str) -> dict[str, str]:
    if fields is None:
        return {}

    result: dict[str, str] = {}
    for key, value in fields.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise TypeError(f"{name} must contain only string keys and values.")
        result[key] = value
    return result


def _require_signature(value: str, *, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"The signer returned an empty or invalid {name}.")
    return value


class CommentListV2RequestProvider:
    """Prepare each ``/rest/o/comment/list/v2`` request independently.

    The signer owns signature generation, including any dependency between
    ``sig``, ``__NS_sig3`` and ``__NStokensig``. No signature is cached here.
    """

    def __init__(
        self,
        *,
        signer: CommentListV2Signer,
        query_fields: Mapping[str, str] | None = None,
        body_fields: Mapping[str, str] | None = None,
        header_fields: Mapping[str, str] | None = None,
    ) -> None:
        self.signer = signer
        self.query_fields = _copy_fields(query_fields, name="query_fields")
        self.body_fields = _copy_fields(body_fields, name="body_fields")
        self.header_fields = _copy_fields(header_fields, name="header_fields")

    def prepare(
        self,
        *,
        query: dict[str, str],
        body: dict[str, str],
        headers: dict[str, str],
    ) -> PreparedMobileRequest:
        unsigned_query = _copy_fields(query, name="query")
        unsigned_body = _copy_fields(body, name="body")
        prepared_headers = _copy_fields(headers, name="headers")

        unsigned_query.update(self.query_fields)
        # The Android profile refreshes timestamp before every request.
        # A saved query template must not replace that current value.
        if "timestamp" in query:
            unsigned_query["timestamp"] = query["timestamp"]
        unsigned_body.update(self.body_fields)
        prepared_headers.update(self.header_fields)

        query_salt = unsigned_query.pop("client_salt", None)
        # fn3/a.g removes the body salt only when the query salt is empty.
        client_salt = query_salt or unsigned_body.pop("client_salt", None) or None

        for params in (unsigned_query, unsigned_body):
            for field in ("sig", "__NS_sig3", "__NStokensig"):
                params.pop(field, None)

        # fn3/a.a removes query keys also present in the form before signing.
        # The captured final URL likewise omits llsid, which is in the form.
        for key in unsigned_body:
            unsigned_query.pop(key, None)
        # Pass copies so a signer cannot change the request that will be sent.
        signatures = self.signer.sign(
            query=dict(unsigned_query),
            body=dict(unsigned_body),
            client_salt=client_salt,
        )
        if not isinstance(signatures, CommentListV2Signatures):
            raise TypeError("The signer must return CommentListV2Signatures.")

        sig = _require_signature(signatures.sig, name="sig")
        sig3 = _require_signature(signatures.sig3, name="__NS_sig3")

        if client_salt and signatures.tokensig is None:
            raise ValueError("The signer omitted __NStokensig for client_salt.")

        if signatures.tokensig is not None:
            tokensig = _require_signature(signatures.tokensig, name="__NStokensig")
            unsigned_body["__NStokensig"] = tokensig

        unsigned_body["sig"] = sig
        unsigned_query["__NS_sig3"] = sig3

        return PreparedMobileRequest(
            query=unsigned_query,
            body=unsigned_body,
            headers=prepared_headers,
        )

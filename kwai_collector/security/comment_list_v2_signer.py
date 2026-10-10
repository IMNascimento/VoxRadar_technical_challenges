"""Sign each Kwai Lite 10.3 comment-list request in app order.

A1_Radar.
"""

from __future__ import annotations

import hashlib
from typing import Protocol

from kwai_collector.security.comment_list_v2_request_provider import (
    CommentListV2Signatures,
)
from kwai_collector.security.comment_list_v2_sig3_canonical import (
    COMMENT_LIST_V2_PATH,
)
from kwai_collector.security.kwai_lite_103_offline_signer import (
    KwaiLite103OfflineSigner,
)
from kwai_collector.security.native_signature_service import NativeSignatureService


def calculate_v10_tokensig(sig: str, client_salt: str | None) -> str | None:
    """Mirror ``r20/g.a``: SHA-256 of UTF-8 ``sig + client_salt``."""
    if not client_salt:
        return None
    return hashlib.sha256((sig + client_salt).encode("utf-8")).hexdigest()


class CommentListV2Sig3Signer(Protocol):
    """Sign the request after ``sig`` and ``__NStokensig`` enter its body."""

    def sign(
        self,
        *,
        method: str,
        path: str,
        query: dict[str, str],
        body: dict[str, str],
    ) -> str: ...


class KwaiLite103CommentListV2Signer:
    """Compose the offline native ``sig`` with an injected sig3 implementation."""

    def __init__(
        self,
        *,
        sig3_signer: CommentListV2Sig3Signer,
        native_signature_service: NativeSignatureService | None = None,
    ) -> None:
        self._sig3_signer = sig3_signer
        self._native_signature_service = (
            native_signature_service
            if native_signature_service is not None
            else NativeSignatureService(KwaiLite103OfflineSigner())
        )

    def sign(
        self,
        *,
        query: dict[str, str],
        body: dict[str, str],
        client_salt: str | None,
    ) -> CommentListV2Signatures:
        # Native input contains unsigned query and body, including the cursor.
        native_query: dict[str, object] = dict(query)
        native_body: dict[str, object] = dict(body)
        sig = self._native_signature_service.sign_request(
            query=native_query,
            body=native_body,
        ).signature
        tokensig = calculate_v10_tokensig(sig, client_salt)

        signed_body = dict(body)
        signed_body["sig"] = sig
        if tokensig is not None:
            signed_body["__NStokensig"] = tokensig

        sig3 = self._sig3_signer.sign(
            method="POST",
            path=COMMENT_LIST_V2_PATH,
            query=dict(query),
            body=signed_body,
        )
        return CommentListV2Signatures(sig=sig, sig3=sig3, tokensig=tokensig)

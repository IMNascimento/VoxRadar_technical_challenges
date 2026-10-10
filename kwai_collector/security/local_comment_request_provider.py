"""Compose the bundled signer without an external signing service.

A1_Radar.
"""

from __future__ import annotations

from collections.abc import Mapping

from kwai_collector.security.comment_list_v2_request_provider import (
    CommentListV2RequestProvider,
)
from kwai_collector.security.comment_list_v2_signer import (
    KwaiLite103CommentListV2Signer,
)
from kwai_collector.security.kwai_lite_103_offline_sig3_signer import (
    KwaiLite103OfflineSig3Signer,
)


def criar_local_comment_request_provider(
    *,
    query_fields: Mapping[str, str] | None = None,
    body_fields: Mapping[str, str] | None = None,
    header_fields: Mapping[str, str] | None = None,
) -> CommentListV2RequestProvider:
    app_version = KwaiLite103OfflineSig3Signer.APP_VERSION
    return CommentListV2RequestProvider(
        signer=KwaiLite103CommentListV2Signer(
            sig3_signer=KwaiLite103OfflineSig3Signer(),
        ),
        query_fields={
            "pkg": KwaiLite103OfflineSig3Signer.APP_PACKAGE,
            "ver": ".".join(app_version.split(".")[:2]),
            "appver": app_version,
            "c": "GOOGLE_PLAY",
            **(query_fields or {}),
        },
        body_fields={
            "os": "android",
            "client_key": "3c2cd3f3",
            **(body_fields or {}),
        },
        header_fields={
            "User-Agent": f"kwai-android/{app_version}",
            **(header_fields or {}),
        },
    )

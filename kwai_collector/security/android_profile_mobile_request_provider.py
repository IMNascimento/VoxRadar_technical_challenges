"""A1_Radar."""

from __future__ import annotations

from kwai_collector.security.android_request_profile import (
    AndroidRequestProfile,
)
from kwai_collector.security.signature_provider import (
    MobileRequestProvider,
    PreparedMobileRequest,
)


class AndroidProfileMobileRequestProvider:
    """
    Adiciona o perfil Android à request antes
    de delegar sua preparação ao provider real.

    Não gera assinatura, sessão, token ou
    identificadores de dispositivo.
    """

    def __init__(
        self,
        delegate: MobileRequestProvider,
        profile: AndroidRequestProfile | None = None,
    ) -> None:
        self.delegate = delegate
        self.profile = profile if profile is not None else AndroidRequestProfile()

    def prepare(
        self,
        *,
        query: dict[str, str],
        body: dict[str, str],
        headers: dict[str, str],
    ) -> PreparedMobileRequest:
        profile_query = self.profile.build_query_fields()

        profile_body = self.profile.build_body_fields()

        profile_headers = self.profile.build_header_fields()

        # O perfil fornece apenas defaults.
        # Dados específicos do endpoint prevalecem.
        prepared_query = {
            **profile_query,
            **query,
        }

        prepared_body = {
            **profile_body,
            **body,
        }

        prepared_headers = {
            **profile_headers,
            **headers,
        }

        return self.delegate.prepare(
            query=prepared_query,
            body=prepared_body,
            headers=prepared_headers,
        )

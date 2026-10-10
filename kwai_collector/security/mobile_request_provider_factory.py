"""A1_Radar."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from kwai_collector.security.android_profile_mobile_request_provider import (
    AndroidProfileMobileRequestProvider,
)
from kwai_collector.security.configured_mobile_request_provider import (
    ConfiguredMobileRequestProvider,
    RequestSignatureService,
)
from kwai_collector.security.http_mobile_request_provider import (
    HttpMobileRequestProvider,
)
from kwai_collector.security.signature_provider import MobileRequestProvider

DEFAULT_AUTH_TIMEOUT: Final = 15.0


def _validar_delegate(
    *,
    delegate: MobileRequestProvider | None,
    query_fields: Mapping[str, str] | None,
    body_fields: Mapping[str, str] | None,
    header_fields: Mapping[str, str] | None,
    signature_service: RequestSignatureService | None,
    signature_field: str | None,
    auth_endpoint: str | None,
    auth_token: str | None,
    auth_timeout: float,
) -> None:
    if delegate is None:
        return

    configuracao_adicional = (
        query_fields is not None
        or body_fields is not None
        or header_fields is not None
        or signature_service is not None
        or signature_field is not None
        or auth_endpoint is not None
        or auth_token is not None
        or auth_timeout != DEFAULT_AUTH_TIMEOUT
    )

    if configuracao_adicional:
        raise ValueError(
            "delegate não pode ser combinado com outra configuração de autenticação."
        )


def _validar_auth_endpoint(
    *,
    auth_endpoint: str | None,
    signature_service: RequestSignatureService | None,
    signature_field: str | None,
) -> None:
    if auth_endpoint and (signature_service is not None or signature_field is not None):
        raise ValueError(
            "auth_endpoint não pode ser combinado com outro serviço de assinatura."
        )


def _criar_delegate(
    *,
    query_fields: Mapping[str, str] | None,
    body_fields: Mapping[str, str] | None,
    header_fields: Mapping[str, str] | None,
    signature_service: RequestSignatureService | None,
    signature_field: str | None,
    auth_endpoint: str | None,
    auth_token: str | None,
    auth_timeout: float,
) -> MobileRequestProvider:
    if auth_endpoint:
        return HttpMobileRequestProvider(
            endpoint=auth_endpoint,
            token=auth_token,
            timeout=auth_timeout,
        )

    return ConfiguredMobileRequestProvider(
        query_fields=query_fields,
        body_fields=body_fields,
        header_fields=header_fields,
        signature_service=signature_service,
        signature_field=signature_field,
    )


def criar_mobile_request_provider(
    *,
    delegate: MobileRequestProvider | None = None,
    query_fields: Mapping[str, str] | None = None,
    body_fields: Mapping[str, str] | None = None,
    header_fields: Mapping[str, str] | None = None,
    signature_service: RequestSignatureService | None = None,
    signature_field: str | None = None,
    auth_endpoint: str | None = None,
    auth_token: str | None = None,
    auth_timeout: float = DEFAULT_AUTH_TIMEOUT,
) -> MobileRequestProvider:
    """
    Cria o provider responsável pela preparação
    de uma requisição mobile.

    A autenticação pode ser fornecida por:

    - um MobileRequestProvider injetado;
    - um serviço HTTP autorizado;
    - um serviço genérico de assinatura injetado.

    Esta factory não conhece nem implementa algoritmos
    específicos de assinatura.
    """

    _validar_delegate(
        delegate=delegate,
        query_fields=query_fields,
        body_fields=body_fields,
        header_fields=header_fields,
        signature_service=signature_service,
        signature_field=signature_field,
        auth_endpoint=auth_endpoint,
        auth_token=auth_token,
        auth_timeout=auth_timeout,
    )

    _validar_auth_endpoint(
        auth_endpoint=auth_endpoint,
        signature_service=signature_service,
        signature_field=signature_field,
    )

    request_provider = (
        delegate
        if delegate is not None
        else _criar_delegate(
            query_fields=query_fields,
            body_fields=body_fields,
            header_fields=header_fields,
            signature_service=signature_service,
            signature_field=signature_field,
            auth_endpoint=auth_endpoint,
            auth_token=auth_token,
            auth_timeout=auth_timeout,
        )
    )

    return AndroidProfileMobileRequestProvider(
        delegate=request_provider,
    )

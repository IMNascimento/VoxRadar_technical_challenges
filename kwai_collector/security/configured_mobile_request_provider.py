"""A1_Radar."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from kwai_collector.security.signature_provider import PreparedMobileRequest


class SignatureResult(Protocol):
    @property
    def signature(self) -> str: ...


class RequestSignatureService(Protocol):
    def sign_request(
        self,
        *,
        query: Mapping[str, object],
        body: Mapping[str, object],
    ) -> SignatureResult: ...


def _normalizar_campos(
    campos: Mapping[str, str] | None,
    *,
    nome: str,
) -> dict[str, str]:
    if campos is None:
        return {}

    resultado: dict[str, str] = {}

    for chave, valor in campos.items():
        if not isinstance(chave, str):
            raise TypeError(f"As chaves de {nome} devem ser strings.")

        if not isinstance(valor, str):
            raise TypeError(f"Os valores de {nome} devem ser strings.")

        resultado[chave] = valor

    return resultado


class ConfiguredMobileRequestProvider:
    """
    Prepara uma requisição mobile usando campos
    explicitamente configurados.

    Opcionalmente recebe um serviço de assinatura
    através de uma abstração injetada.

    Este módulo não implementa algoritmo de assinatura.
    """

    def __init__(
        self,
        *,
        query_fields: Mapping[str, str] | None = None,
        body_fields: Mapping[str, str] | None = None,
        header_fields: Mapping[str, str] | None = None,
        signature_service: RequestSignatureService | None = None,
        signature_field: str | None = None,
    ) -> None:
        self.query_fields = _normalizar_campos(
            query_fields,
            nome="query_fields",
        )
        self.body_fields = _normalizar_campos(
            body_fields,
            nome="body_fields",
        )
        self.header_fields = _normalizar_campos(
            header_fields,
            nome="header_fields",
        )

        self.signature_service = signature_service
        self.signature_field = signature_field

        if self.signature_service is not None and not self.signature_field:
            raise ValueError(
                "signature_field deve ser informado "
                "quando signature_service estiver configurado."
            )

    def prepare(
        self,
        *,
        query: dict[str, str],
        body: dict[str, str],
        headers: dict[str, str],
    ) -> PreparedMobileRequest:
        prepared_query = dict(query)
        prepared_body = dict(body)
        prepared_headers = dict(headers)

        prepared_query.update(self.query_fields)
        prepared_body.update(self.body_fields)
        prepared_headers.update(self.header_fields)

        if self.signature_service is not None:
            signature_result = self.signature_service.sign_request(
                query=prepared_query,
                body=prepared_body,
            )

            if self.signature_field is None:
                raise RuntimeError("signature_field não configurado.")

            prepared_body[self.signature_field] = signature_result.signature

        return PreparedMobileRequest(
            query=prepared_query,
            body=prepared_body,
            headers=prepared_headers,
        )

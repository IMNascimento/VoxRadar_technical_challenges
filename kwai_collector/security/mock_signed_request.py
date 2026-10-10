"""A1_Radar."""

from __future__ import annotations

from dataclasses import dataclass

from kwai_collector.security.mobile_request_prep import (
    preparar_requisicao_mobile,
)
from kwai_collector.security.mock_signature_service import (
    MockSignatureService,
)


@dataclass(frozen=True)
class MockSignedRequest:
    query: dict[str, str]
    body: dict[str, str]
    client_salt: str | None
    mock_sig3: str


def preparar_requisicao_mock_assinada(
    query: dict[str, object],
    body: dict[str, object],
    signature_service: (MockSignatureService | None) = None,
) -> MockSignedRequest:
    prepared = preparar_requisicao_mobile(
        query=query,
        body=body,
    )

    service = (
        signature_service if signature_service is not None else MockSignatureService()
    )

    mock_sig3 = service.generate_sig3(
        query=prepared.query,
        body=prepared.body,
        client_salt=prepared.client_salt,
    )

    return MockSignedRequest(
        query=prepared.query,
        body=prepared.body,
        client_salt=prepared.client_salt,
        mock_sig3=mock_sig3,
    )

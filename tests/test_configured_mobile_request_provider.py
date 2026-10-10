from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import pytest

from kwai_collector.security.configured_mobile_request_provider import (
    ConfiguredMobileRequestProvider,
)
from kwai_collector.security.signature_provider import (
    PreparedMobileRequest,
)


@dataclass(frozen=True)
class FakeSignatureResult:
    signature: str


class FakeRequestSignatureService:
    def __init__(
        self,
        signature: str = "assinatura-falsa",
    ) -> None:
        self.signature = signature
        self.received_query: dict[str, object] | None = None
        self.received_body: dict[str, object] | None = None

    def sign_request(
        self,
        *,
        query: Mapping[str, object],
        body: Mapping[str, object],
    ) -> FakeSignatureResult:
        self.received_query = dict(query)
        self.received_body = dict(body)

        return FakeSignatureResult(
            signature=self.signature,
        )


class FakeSignatureServiceError(RuntimeError):
    pass


class FailingRequestSignatureService:
    def sign_request(
        self,
        *,
        query: Mapping[str, object],
        body: Mapping[str, object],
    ) -> FakeSignatureResult:
        raise FakeSignatureServiceError("Serviço de assinatura indisponível.")


def test_prepare_adiciona_campos_configurados() -> None:
    provider = ConfiguredMobileRequestProvider(
        query_fields={
            "extra_query": "query_value",
        },
        body_fields={
            "extra_body": "body_value",
        },
        header_fields={
            "Authorization": "Bearer teste",
        },
    )

    query = {
        "llsid": "123",
    }

    body = {
        "photoId": "999",
    }

    headers = {
        "Accept": "application/json",
    }

    resultado = provider.prepare(
        query=query,
        body=body,
        headers=headers,
    )

    assert isinstance(
        resultado,
        PreparedMobileRequest,
    )

    assert resultado.query == {
        "llsid": "123",
        "extra_query": "query_value",
    }

    assert resultado.body == {
        "photoId": "999",
        "extra_body": "body_value",
    }

    assert resultado.headers == {
        "Accept": "application/json",
        "Authorization": "Bearer teste",
    }


def test_prepare_nao_altera_dicionarios_originais() -> None:
    provider = ConfiguredMobileRequestProvider(
        query_fields={
            "novo": "valor",
        },
    )

    query = {
        "original": "1",
    }

    body = {
        "body": "2",
    }

    headers = {
        "Accept": "application/json",
    }

    provider.prepare(
        query=query,
        body=body,
        headers=headers,
    )

    assert query == {
        "original": "1",
    }

    assert body == {
        "body": "2",
    }

    assert headers == {
        "Accept": "application/json",
    }


def test_campos_configurados_sobrescrevem_valores() -> None:
    provider = ConfiguredMobileRequestProvider(
        query_fields={
            "campo": "configurado",
        },
        body_fields={
            "campo": "configurado",
        },
        header_fields={
            "Campo": "configurado",
        },
    )

    resultado = provider.prepare(
        query={
            "campo": "original",
        },
        body={
            "campo": "original",
        },
        headers={
            "Campo": "original",
        },
    )

    assert resultado.query["campo"] == "configurado"
    assert resultado.body["campo"] == "configurado"
    assert resultado.headers["Campo"] == "configurado"


def test_provider_sem_configuracao() -> None:
    provider = ConfiguredMobileRequestProvider()

    resultado = provider.prepare(
        query={
            "a": "1",
        },
        body={
            "b": "2",
        },
        headers={
            "c": "3",
        },
    )

    assert resultado.query == {
        "a": "1",
    }

    assert resultado.body == {
        "b": "2",
    }

    assert resultado.headers == {
        "c": "3",
    }


def test_rejeita_valor_nao_string() -> None:
    with pytest.raises(
        TypeError,
        match="valores",
    ):
        ConfiguredMobileRequestProvider(
            header_fields={
                "X-Test": 123,  # type: ignore[dict-item]
            },
        )


def test_rejeita_chave_nao_string() -> None:
    with pytest.raises(
        TypeError,
        match="chaves",
    ):
        ConfiguredMobileRequestProvider(
            query_fields={
                123: "valor",  # type: ignore[dict-item]
            },
        )


def test_signature_service_adiciona_campo_no_body() -> None:
    service = FakeRequestSignatureService()

    provider = ConfiguredMobileRequestProvider(
        query_fields={
            "extra_query": "1",
        },
        body_fields={
            "extra_body": "2",
        },
        signature_service=service,
        signature_field="test_sig",
    )

    resultado = provider.prepare(
        query={
            "llsid": "123",
        },
        body={
            "photoId": "999",
        },
        headers={},
    )

    assert resultado.body["test_sig"] == "assinatura-falsa"

    assert service.received_query == {
        "llsid": "123",
        "extra_query": "1",
    }

    assert service.received_body == {
        "photoId": "999",
        "extra_body": "2",
    }


def test_assinatura_nao_participa_da_propria_entrada() -> None:
    service = FakeRequestSignatureService()

    provider = ConfiguredMobileRequestProvider(
        signature_service=service,
        signature_field="test_sig",
    )

    resultado = provider.prepare(
        query={
            "a": "1",
        },
        body={
            "b": "2",
        },
        headers={},
    )

    assert service.received_query == {
        "a": "1",
    }

    assert service.received_body == {
        "b": "2",
    }

    assert "test_sig" not in (service.received_body or {})

    assert resultado.body["test_sig"] == "assinatura-falsa"


def test_signature_field_obrigatorio_com_service() -> None:
    service = FakeRequestSignatureService()

    with pytest.raises(
        ValueError,
        match="signature_field",
    ):
        ConfiguredMobileRequestProvider(
            signature_service=service,
        )


def test_erro_do_signature_service_e_propagado() -> None:
    service = FailingRequestSignatureService()

    provider = ConfiguredMobileRequestProvider(
        signature_service=service,
        signature_field="test_sig",
    )

    with pytest.raises(
        FakeSignatureServiceError,
        match="indisponível",
    ):
        provider.prepare(
            query={
                "a": "1",
            },
            body={
                "b": "2",
            },
            headers={},
        )

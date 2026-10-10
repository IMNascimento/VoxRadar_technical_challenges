"""A1_Radar."""

from __future__ import annotations

from typing import Any

import httpx

from kwai_collector.security.mock_signed_request import (
    preparar_requisicao_mock_assinada,
)


class MockCommentClient:
    """
    Cliente HTTP utilizado exclusivamente para testes
    e ambiente de homologação.

    Ele utiliza a infraestrutura de assinatura mock do
    projeto e não representa autenticação real do Kwai.
    """

    def __init__(
        self,
        base_url: str,
        timeout: float = 20.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def post(
        self,
        endpoint: str,
        query: dict[str, object],
        body: dict[str, object],
    ) -> dict[str, Any]:
        """
        Prepara uma requisição mock assinada e realiza
        o POST para o servidor de homologação.

        A assinatura utilizada aqui é apenas:

            __MOCK_NS_sig3

        e não deve ser confundida com campos reais de
        autenticação.
        """

        signed = preparar_requisicao_mock_assinada(
            query=query,
            body=body,
        )

        headers = {
            "Accept": "application/json",
            "Content-Type": ("application/x-www-form-urlencoded"),
            "X-Mock-Signature": signed.mock_sig3,
        }

        payload = dict(signed.body)

        payload["__MOCK_NS_sig3"] = signed.mock_sig3

        url = f"{self.base_url}/{endpoint.lstrip('/')}"

        with httpx.Client(
            timeout=self.timeout,
            trust_env=False,
        ) as client:
            response = client.post(
                url,
                params=signed.query,
                data=payload,
                headers=headers,
            )

        response.raise_for_status()

        data = response.json()

        if not isinstance(
            data,
            dict,
        ):
            raise TypeError("Resposta de homologação não é um objeto JSON.")

        return data

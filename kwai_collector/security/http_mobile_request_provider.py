"""A1_Radar."""

from __future__ import annotations

from typing import Any

import httpx

from kwai_collector.security.signature_provider import (
    PreparedMobileRequest,
)


class HttpMobileRequestProvider:
    """
    Provider que delega a preparação/autenticação
    da request mobile para um serviço HTTP externo.

    O serviço remoto deve receber query/body/headers
    e devolver esses três objetos já preparados.

    Este módulo NÃO implementa algoritmo de assinatura.
    """

    def __init__(
        self,
        endpoint: str,
        *,
        token: str | None = None,
        client: httpx.Client | None = None,
        timeout: float = 15.0,
    ) -> None:
        self.endpoint = endpoint

        self.token = token

        self.client = client or httpx.Client(
            timeout=timeout,
        )

    def prepare(
        self,
        *,
        query: dict[str, str],
        body: dict[str, str],
        headers: dict[str, str],
    ) -> PreparedMobileRequest:
        request_headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        if self.token:
            request_headers["Authorization"] = f"Bearer {self.token}"

        response = self.client.post(
            self.endpoint,
            json={
                "query": dict(query),
                "body": dict(body),
                "headers": dict(headers),
            },
            headers=request_headers,
        )

        response.raise_for_status()

        try:
            data: Any = response.json()

        except ValueError as exc:
            raise RuntimeError(
                "O serviço de preparação mobile retornou uma resposta não JSON."
            ) from exc

        if not isinstance(
            data,
            dict,
        ):
            raise TypeError("Resposta inválida do serviço mobile.")

        prepared_query = data.get("query")

        prepared_body = data.get("body")

        prepared_headers = data.get("headers")

        if not isinstance(
            prepared_query,
            dict,
        ):
            raise TypeError("O campo 'query' retornado deve ser um objeto.")

        if not isinstance(
            prepared_body,
            dict,
        ):
            raise TypeError("O campo 'body' retornado deve ser um objeto.")

        if not isinstance(
            prepared_headers,
            dict,
        ):
            raise TypeError("O campo 'headers' retornado deve ser um objeto.")

        return PreparedMobileRequest(
            query={str(key): str(value) for key, value in prepared_query.items()},
            body={str(key): str(value) for key, value in prepared_body.items()},
            headers={str(key): str(value) for key, value in prepared_headers.items()},
        )

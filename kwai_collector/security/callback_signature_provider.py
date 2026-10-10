"""A1_Radar."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from kwai_collector.security.signature_provider import (
    PreparedMobileRequest,
)

SignatureCallback = Callable[
    [
        dict[str, str],
        dict[str, str],
        str | None,
    ],
    Mapping[str, str],
]


MobileRequestCallback = Callable[
    [
        dict[str, str],
        dict[str, str],
        dict[str, str],
    ],
    PreparedMobileRequest,
]


def _normalize_mapping(
    value: Mapping[str, str],
    *,
    name: str,
) -> dict[str, str]:
    resultado: dict[str, str] = {}

    for chave, valor in value.items():
        if not isinstance(
            chave,
            str,
        ):
            raise TypeError(f"As chaves de {name} devem ser strings.")

        if not isinstance(
            valor,
            str,
        ):
            raise TypeError(f"Os valores de {name} devem ser strings.")

        resultado[chave] = valor

    return resultado


class CallbackSignatureProvider:
    """
    Adapter legado entre o cliente HTTP e uma
    fonte externa de campos adicionais.

    Mantido para compatibilidade com componentes
    antigos do projeto.
    """

    def __init__(
        self,
        callback: SignatureCallback,
    ) -> None:
        self._callback = callback

    def sign(
        self,
        query: dict[str, str],
        body: dict[str, str],
        client_salt: str | None,
    ) -> dict[str, str]:
        resultado = self._callback(
            dict(query),
            dict(body),
            client_salt,
        )

        if not isinstance(
            resultado,
            Mapping,
        ):
            raise TypeError("O callback deve retornar um Mapping.")

        return _normalize_mapping(
            resultado,
            name="resultado",
        )


class CallbackMobileRequestProvider:
    """
    Adapter para o fluxo mobile novo.

    O callback recebe cópias de query, body
    e headers e deve devolver uma
    PreparedMobileRequest.

    Este adapter não implementa geração de
    credenciais ou assinaturas. Ele apenas
    fornece a fronteira de injeção de dependência.
    """

    def __init__(
        self,
        callback: MobileRequestCallback,
    ) -> None:
        self._callback = callback

    def prepare(
        self,
        *,
        query: dict[str, str],
        body: dict[str, str],
        headers: dict[str, str],
    ) -> PreparedMobileRequest:
        resultado = self._callback(
            dict(query),
            dict(body),
            dict(headers),
        )

        if not isinstance(
            resultado,
            PreparedMobileRequest,
        ):
            raise TypeError("O callback mobile deve retornar PreparedMobileRequest.")

        prepared_query = _normalize_mapping(
            resultado.query,
            name="query",
        )

        prepared_body = _normalize_mapping(
            resultado.body,
            name="body",
        )

        prepared_headers = _normalize_mapping(
            resultado.headers,
            name="headers",
        )

        return PreparedMobileRequest(
            query=prepared_query,
            body=prepared_body,
            headers=prepared_headers,
        )

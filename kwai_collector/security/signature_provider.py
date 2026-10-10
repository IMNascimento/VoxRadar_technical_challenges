"""A1_Radar."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class SignatureProvider(Protocol):
    """
    Contrato legado da camada de assinatura.

    Mantido para compatibilidade com código antigo
    e testes existentes.

    Recebe uma requisição já normalizada e retorna
    campos adicionais que devem ser incorporados
    à requisição final.

    Clientes HTTP novos devem preferir
    MobileRequestProvider.
    """

    def sign(
        self,
        query: dict[str, str],
        body: dict[str, str],
        client_salt: str | None,
    ) -> dict[str, str]: ...


@dataclass(frozen=True)
class PreparedMobileRequest:
    """
    Representa a requisição mobile final,
    pronta para ser enviada pelo cliente HTTP.

    Contém:

        query final
        body final
        headers finais
    """

    query: dict[str, str]
    body: dict[str, str]
    headers: dict[str, str]


# Alias de compatibilidade.
#
# Alguns trechos mais novos do projeto podem usar
# PreparedMobileHttpRequest, enquanto componentes
# existentes importam PreparedMobileRequest.
#
# Os dois nomes representam exatamente o mesmo tipo.
PreparedMobileHttpRequest = PreparedMobileRequest


class MobileRequestProvider(Protocol):
    """
    Fronteira de alto nível utilizada pelos
    clientes HTTP mobile.

    Recebe query, body e headers e devolve uma
    requisição completamente preparada para envio.
    """

    def prepare(
        self,
        *,
        query: dict[str, str],
        body: dict[str, str],
        headers: dict[str, str],
    ) -> PreparedMobileRequest: ...

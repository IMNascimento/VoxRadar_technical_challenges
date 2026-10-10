"""A1_Radar."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PreparedSignatureInput:
    """
    Representa os dados normalizados que serão entregues
    à próxima etapa de preparação da requisição mobile.

    Esta estrutura ainda não representa uma requisição HTTP
    final. Ela contém apenas:

    - query normalizada;
    - body normalizado;
    - client_salt separado dos parâmetros.
    """

    query: dict[str, str]
    body: dict[str, str]
    client_salt: str | None


def _normalizar_valor(
    valor: object,
) -> str:
    """
    Converte valores da requisição para representação textual.
    """

    if valor is None:
        return ""

    if isinstance(valor, bool):
        return "true" if valor else "false"

    return str(valor)


def _normalizar_mapa(
    valores: dict[str, object],
) -> dict[str, str]:
    """
    Normaliza todas as chaves e valores de um mapa.
    """

    return {str(chave): _normalizar_valor(valor) for chave, valor in valores.items()}


def _remover_coordenadas(
    query: dict[str, str],
) -> None:
    """
    Remove coordenadas que não permanecem após
    a preparação da requisição.
    """

    query.pop(
        "lat",
        None,
    )

    query.pop(
        "lon",
        None,
    )


def _extrair_client_salt(
    *,
    query: dict[str, str],
    body: dict[str, str],
) -> str | None:
    """
    Remove client_salt da query e do body.

    Quando existe nos dois lugares, o valor do body
    prevalece.
    """

    query_client_salt = query.pop(
        "client_salt",
        None,
    )

    body_client_salt = body.pop(
        "client_salt",
        None,
    )

    client_salt = body_client_salt or query_client_salt

    if not client_salt:
        return None

    return client_salt


def _aplicar_precedencia_body(
    *,
    query: dict[str, str],
    body: dict[str, str],
) -> None:
    """
    Remove da query qualquer chave que também exista
    no body.

    Regra:

        body > query
    """

    for chave in body:
        query.pop(
            chave,
            None,
        )


def preparar_requisicao_mobile(
    query: dict[str, object],
    body: dict[str, object],
) -> PreparedSignatureInput:
    """
    Normaliza os dados até a fronteira da próxima etapa.

    Fluxo:

        query + body
              ↓
        normalização
              ↓
        remoção de lat/lon
              ↓
        separação de client_salt
              ↓
        precedência do body
              ↓
        PreparedSignatureInput

    Esta função não produz a requisição HTTP final.
    """

    query_normalizada = _normalizar_mapa(query)

    body_normalizado = _normalizar_mapa(body)

    _remover_coordenadas(query_normalizada)

    client_salt = _extrair_client_salt(
        query=query_normalizada,
        body=body_normalizado,
    )

    _aplicar_precedencia_body(
        query=query_normalizada,
        body=body_normalizado,
    )

    return PreparedSignatureInput(
        query=query_normalizada,
        body=body_normalizado,
        client_salt=client_salt,
    )

"""A1_Radar."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class NativeSignatureInput:
    """
    Representa os parÃ¢metros preparados atÃ© a
    fronteira Java -> native.

    Este mÃ³dulo NÃƒO calcula a assinatura.
    """

    params: dict[str, str]
    canonical_text: str
    canonical_bytes: bytes


def _normalizar_valor(
    valor: object,
) -> str:
    if valor is None:
        return ""

    if isinstance(valor, bool):
        return "true" if valor else "false"

    return str(valor)


def _mesclar_parametros(
    *,
    query: Mapping[str, object],
    body: Mapping[str, object],
) -> dict[str, str]:
    """
    Cria uma visÃ£o mesclada dos parÃ¢metros.

    Em caso de chave repetida, o body prevalece nesta visÃ£o.
    A canonicalizaÃ§Ã£o usa query e body separadamente para
    preservar ambas as entradas.
    """

    resultado: dict[str, str] = {}

    for chave, valor in query.items():
        resultado[str(chave)] = _normalizar_valor(valor)

    for chave, valor in body.items():
        resultado[str(chave)] = _normalizar_valor(valor)

    return resultado


def _canonicalizar(
    *,
    query: Mapping[str, object],
    body: Mapping[str, object],
) -> str:
    """
    Fluxo observado no Java:

    1. cada entrada da query e do body vira "key=value";
    2. as strings completas sÃ£o ordenadas;
    3. tudo Ã© concatenado sem separador.

    Chaves presentes nos dois mapas participam duas vezes.
    """

    partes = [
        f"{chave}={_normalizar_valor(valor)}"
        for origem in (query, body)
        for chave, valor in origem.items()
    ]

    # Java compares unsigned UTF-16 code units, including surrogate pairs.
    partes.sort(key=lambda value: value.encode("utf-16-be", errors="surrogatepass"))

    return "".join(partes)


def preparar_entrada_nativa(
    *,
    query: Mapping[str, object],
    body: Mapping[str, object],
) -> NativeSignatureInput:
    """
    Prepara os dados atÃ© a fronteira onde
    os bytes seriam enviados ao cÃ³digo nativo.

    NÃ£o executa getClock e nÃ£o gera sig.
    """

    params = _mesclar_parametros(
        query=query,
        body=body,
    )

    canonical_text = _canonicalizar(
        query=query,
        body=body,
    )

    canonical_bytes = canonical_text.encode("utf-8")

    return NativeSignatureInput(
        params=params,
        canonical_text=canonical_text,
        canonical_bytes=canonical_bytes,
    )

"""A1_Radar."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from kwai_collector.security.native_signature_boundary import (
    NativeSignatureInput,
    preparar_entrada_nativa,
)
from kwai_collector.security.native_signer import (
    NativeSigner,
)


@dataclass(frozen=True)
class NativeSignatureResult:
    """
    Resultado da passagem pela fronteira
    de assinatura.

    MantÃ©m tanto a entrada canonicalizada
    quanto o valor retornado pelo signer.
    """

    input: NativeSignatureInput
    signature: str


class NativeSignatureService:
    """
    Orquestra:

    query/body
        ->
    canonicalizaÃ§Ã£o
        ->
    NativeSigner

    Este serviÃ§o nÃ£o conhece o algoritmo
    interno do signer.
    """

    def __init__(
        self,
        signer: NativeSigner,
    ) -> None:
        self._signer = signer

    def sign_request(
        self,
        *,
        query: Mapping[str, object],
        body: Mapping[str, object],
    ) -> NativeSignatureResult:
        prepared = preparar_entrada_nativa(
            query=query,
            body=body,
        )

        signature = self._signer.sign(prepared.canonical_bytes)

        return NativeSignatureResult(
            input=prepared,
            signature=signature,
        )

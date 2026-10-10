"""A1_Radar."""

from __future__ import annotations

from typing import Protocol


class NativeSignerUnavailableError(RuntimeError):
    """
    Indica que não existe uma implementação nativa
    de assinatura configurada no ambiente atual.
    """


class NativeSigner(Protocol):
    """
    Contrato para uma implementação externa/nativa
    responsável por processar os bytes canonicalizados.

    Este módulo define somente a interface.
    """

    def sign(
        self,
        canonical_bytes: bytes,
    ) -> str: ...


class UnavailableNativeSigner:
    """
    Implementação padrão usada quando nenhum mecanismo
    nativo autorizado está disponível.

    Ela falha explicitamente em vez de fabricar uma
    assinatura inválida.
    """

    def sign(
        self,
        canonical_bytes: bytes,
    ) -> str:
        del canonical_bytes

        raise NativeSignerUnavailableError("Nenhum NativeSigner foi configurado.")

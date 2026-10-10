"""A1_Radar."""

from __future__ import annotations

from collections.abc import Mapping

from kwai_collector.security.mock_signer_engine import (
    MockSignerEngine,
)
from kwai_collector.security.signature_provider import (
    SignatureProvider,
)


class MockSignatureService:
    """
    Adaptador de homologação para o
    SignatureProvider.
    """

    def __init__(
        self,
        signer: SignatureProvider | None = None,
    ) -> None:
        self._signer = signer if signer is not None else MockSignerEngine()

    @staticmethod
    def normalize(
        params: Mapping[str, str],
    ) -> str:
        partes = [f"{chave}={params[chave]}" for chave in sorted(params)]

        return "&".join(partes)

    def generate_sig3(
        self,
        query: Mapping[str, str],
        body: Mapping[str, str],
        client_salt: str | None = None,
    ) -> str:
        campos = self._signer.sign(
            query=dict(query),
            body=dict(body),
            client_salt=client_salt,
        )

        token = campos.get("__MOCK_NS_sig3")

        if not token:
            raise RuntimeError("Mock signer não retornou __MOCK_NS_sig3.")

        return token

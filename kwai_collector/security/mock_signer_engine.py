"""A1_Radar."""

from __future__ import annotations

import hashlib

from kwai_collector.security.signature_provider import (
    SignatureProvider,
)


class MockSignerEngine(SignatureProvider):
    """
    Implementação fictícia de SignatureProvider.

    Exclusivamente para testes, homologação
    e validação da arquitetura interna.

    IMPORTANTE:
    - não reproduz a assinatura real do Kwai;
    - não deve ser utilizado como mecanismo
      de autenticação contra a API real;
    - gera valores determinísticos apenas para
      permitir testar paginação e renovação
      das assinaturas por request.
    """

    MOCK_SALT = "mock_salt_123"

    def __init__(
        self,
        secret: str | None = None,
    ) -> None:
        self._secret = secret if secret is not None else self.MOCK_SALT

    @staticmethod
    def _rotate_left(
        value: int,
        shift: int,
    ) -> int:
        """
        Rotação de 32 bits para a esquerda.
        """

        value &= 0xFFFFFFFF
        shift &= 31

        if shift == 0:
            return value

        return ((value << shift) | (value >> (32 - shift))) & 0xFFFFFFFF

    @staticmethod
    def _rotate_right(
        value: int,
        shift: int,
    ) -> int:
        """
        Rotação de 32 bits para a direita.
        """

        value &= 0xFFFFFFFF
        shift &= 31

        if shift == 0:
            return value

        return ((value >> shift) | (value << (32 - shift))) & 0xFFFFFFFF

    def _bitwise_mix(
        self,
        data: bytes,
    ) -> bytes:
        """
        Mistura fictícia utilizada somente
        para produzir tokens de teste estáveis.
        """

        state_a = 0x13579BDF
        state_b = 0x2468ACE0
        state_c = 0xA5A5A5A5
        state_d = 0x5A5A5A5A

        for index, byte in enumerate(data):
            shift = (index % 13) + 1

            state_a ^= byte << (index % 8)

            state_a = self._rotate_left(
                state_a,
                shift,
            )

            state_b ^= state_a >> (index % 7)

            state_b = self._rotate_right(
                state_b,
                (index % 11) + 1,
            )

            state_c ^= state_a ^ state_b ^ byte

            state_c = self._rotate_left(
                state_c,
                5,
            )

            state_d ^= state_c >> 3

            state_d ^= byte << 16

            state_d = self._rotate_right(
                state_d,
                7,
            )

            state_a &= 0xFFFFFFFF
            state_b &= 0xFFFFFFFF
            state_c &= 0xFFFFFFFF
            state_d &= 0xFFFFFFFF

        return b"".join(
            value.to_bytes(
                4,
                byteorder="big",
            )
            for value in (
                state_a,
                state_b,
                state_c,
                state_d,
            )
        )

    @staticmethod
    def _normalize(
        query: dict[str, str],
        body: dict[str, str],
    ) -> str:
        """
        Consolida os parâmetros da request.

        O body prevalece sobre query.

        Os campos são ordenados para que a mesma
        request sempre gere o mesmo resultado
        durante os testes.
        """

        combined = dict(query)

        combined.update(body)

        return "&".join(f"{key}={combined[key]}" for key in sorted(combined))

    def _generate_mock_token(
        self,
        *,
        normalized_string: str,
        client_salt: str | None,
        namespace: str,
    ) -> str:
        """
        Gera um token fictício determinístico
        de 32 caracteres hexadecimais.

        namespace separa os tokens simulados:

            mock_sig
            mock_sig3
        """

        material = (
            f"{namespace}:{self._secret}:{client_salt or ''}:{normalized_string}"
        ).encode()

        sha_digest = hashlib.sha256(material).digest()

        mixed = self._bitwise_mix(sha_digest)

        final_material = (
            namespace.encode("utf-8")
            + mixed
            + sha_digest
            + self._secret.encode("utf-8")
        )

        # SHA-256 produz 64 caracteres hex.
        # O contrato dos mocks do projeto espera 32.
        return hashlib.sha256(final_material).hexdigest()[:32]

    def sign(
        self,
        query: dict[str, str],
        body: dict[str, str],
        client_salt: str | None,
    ) -> dict[str, str]:
        """
        Produz valores fictícios para testes.

        Alterações no pcursor ou em qualquer
        parâmetro da request geram novos valores.

        Retorno:

            {
                "sig": "...",
                "__MOCK_NS_sig3": "...",
            }

        Os valores NÃO são assinaturas reais.
        """

        normalized = self._normalize(
            query=query,
            body=body,
        )

        mock_sig = self._generate_mock_token(
            normalized_string=normalized,
            client_salt=client_salt,
            namespace="mock_sig",
        )

        mock_sig3 = self._generate_mock_token(
            normalized_string=normalized,
            client_salt=client_salt,
            namespace="mock_sig3",
        )

        return {
            "sig": mock_sig,
            "__MOCK_NS_sig3": mock_sig3,
        }

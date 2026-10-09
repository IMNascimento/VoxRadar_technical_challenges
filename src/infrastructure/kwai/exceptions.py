"""Exceções da camada de infraestrutura do coletor."""

from __future__ import annotations

from ...domain.exceptions.domain_exceptions import KwaiCollectorError


class KwaiTransportError(KwaiCollectorError):
    """Falha de transporte na comunicação com o Kwai."""


class UnexpectedResponseError(KwaiCollectorError):
    """Resposta do Kwai fora do formato esperado."""


class KwaiApiError(KwaiCollectorError):
    """A API do Kwai respondeu com um código de erro de negócio.

    O Kwai retorna HTTP 200 mesmo em falhas, sinalizando o problema no campo
    ``result`` do corpo. Esta exceção carrega esse código.
    """

    def __init__(self, message: str, *, result: int | None = None) -> None:
        """Inicializa a exceção com a mensagem e o código de negócio.

        Args:
            message: descrição legível da falha.
            result: código devolvido no campo ``result``, quando houver.
        """
        super().__init__(message)
        self.result = result

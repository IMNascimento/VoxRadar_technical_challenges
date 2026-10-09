"""Porta de leitura das postagens de um perfil."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ...domain.value_objects.cursor import Cursor
from ...domain.value_objects.identifiers import Handle, UserId
from ...domain.value_objects.iso_timestamp import IsoTimestamp
from ..dtos.pages import ProfilePage


class IProfileApiPort(ABC):
    """Contrato de leitura das postagens de um perfil — agnóstico de transporte.

    São dois passos: resolver o handle para o id numérico (o feed não aceita
    handle) e então paginar o feed, uma página por chamada, com o tamanho que o
    endpoint aceita.
    """

    @abstractmethod
    def resolve_user(self, handle: Handle) -> UserId:
        """Resolve o handle para o id numérico usado pelo feed.

        Raises:
            ExternalServiceError: se o serviço externo falhar no transporte, no
                formato da resposta ou com erro de negócio.
        """

    @abstractmethod
    def fetch_profile_page(
        self,
        user_id: UserId,
        *,
        cursor: Cursor,
        collected_at: IsoTimestamp,
    ) -> ProfilePage:
        """Busca uma página do feed do usuário.

        Raises:
            ExternalServiceError: se o serviço externo falhar no transporte, no
                formato da resposta ou com erro de negócio.
        """

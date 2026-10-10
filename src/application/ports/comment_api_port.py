"""Porta de leitura dos comentários de uma postagem (raízes e respostas)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ...domain.value_objects.cursor import Cursor
from ...domain.value_objects.identifiers import CommentId
from ...domain.value_objects.iso_timestamp import IsoTimestamp
from ...domain.value_objects.post_reference import PostReference
from ..dtos.pages import CommentPage, SubCommentPage


class ICommentApiPort(ABC):
    """Contrato de leitura de comentários — agnóstico de transporte.

    Uma página por chamada, com o tamanho que o endpoint aceita; decidir o fim
    da paginação é responsabilidade do caso de uso.
    """

    @abstractmethod
    def fetch_page(
        self,
        post: PostReference,
        *,
        cursor: Cursor,
        collected_at: IsoTimestamp,
    ) -> CommentPage:
        """Busca uma página de comentários de raiz da postagem.

        Raises:
            ExternalServiceError: se o serviço externo falhar no transporte, no
                formato da resposta ou com erro de negócio.
        """

    @abstractmethod
    def fetch_sub_page(
        self,
        post: PostReference,
        *,
        root_comment_id: CommentId,
        cursor: Cursor,
        collected_at: IsoTimestamp,
    ) -> SubCommentPage:
        """Busca uma página de respostas de um comentário raiz.

        Raises:
            ExternalServiceError: se o serviço externo falhar no transporte, no
                formato da resposta ou com erro de negócio.
        """

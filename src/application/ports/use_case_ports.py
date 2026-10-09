"""Portas de entrada para executar as coletas sem conhecer suas implementações."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator

from ...domain.entities.comment import Comment
from ...domain.entities.post import Post
from ..dtos.collection_result import CollectionResult
from ..dtos.commands import CommentCollectionCommand, ProfileCollectionCommand, SearchCommand


class ISearchPostsPort(ABC):
    """Define a busca agregada por palavras-chave."""

    @abstractmethod
    def execute(self, command: SearchCommand) -> CollectionResult[Post]:
        """Entrega as postagens e uma eventual falha com resultado parcial."""


class ICollectUserPostsPort(ABC):
    """Define a coleta das postagens de um perfil."""

    @abstractmethod
    def execute(self, command: ProfileCollectionCommand) -> list[Post]:
        """Entrega postagens ou propaga a falha, preservando eventual parcial.

        Raises:
            KwaiCollectorError: se a coleta falhar antes de obter postagens.
            CollectionInterruptedError: se a coleta falhar com postagens já obtidas.
        """


class ICollectCommentVersionsPort(ABC):
    """Define a coleta das versões de comentários de uma postagem."""

    @abstractmethod
    def execute(self, command: CommentCollectionCommand) -> Iterator[CollectionResult[Comment]]:
        """Entrega as versões solicitadas, com falha e parcial explícitos por etapa."""


class ICollectProfileBundlePort(ABC):
    """Define a coleta combinada de postagens e comentários de um perfil."""

    @abstractmethod
    def execute(
        self, command: ProfileCollectionCommand
    ) -> Iterator[CollectionResult[Post | Comment]]:
        """Entrega postagens antes dos comentários, isolando falhas por postagem."""

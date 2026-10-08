"""Portas da camada de aplicação para leitura dos dados do Kwai.

As portas existem como *seam* de I/O: os casos de uso dependem destes
``Protocol`` (e não dos adapters HTTP), o que os mantém testáveis sem ``respx``
e sem rede. Elas também separam a **regra de paginação** da **execução de
rede**: o adapter busca uma página, e o caso de uso decide quando parar.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..domain.value_objects.cursor import Cursor
from ..domain.value_objects.identifiers import CommentId, Handle, PhotoId, UserId
from ..domain.value_objects.iso_timestamp import IsoTimestamp
from .models import Comment, Post


@dataclass(frozen=True)
class RootComment:
    """Um comentário de raiz e o total de respostas que a API declara.

    Attributes:
        comentario: comentário raiz já mapeado para o contrato.
        respostas_declaradas: valor de ``sub_comment_count`` informado pela API,
            ou ``None`` quando ausente. É o total **declarado**, que pode
            diferir do que a coleta entrega.
    """

    comentario: Comment
    respostas_declaradas: int | None


@dataclass(frozen=True)
class CommentPage:
    """Uma página de comentários de raiz devolvida pela API móvel.

    Attributes:
        comments: raízes já mapeadas, com o total declarado de respostas.
        next_cursor: cursor para a próxima página.
    """

    comments: list[RootComment]
    next_cursor: Cursor


@dataclass(frozen=True)
class SubComment:
    """Uma resposta (sub-comentário) de um comentário raiz.

    Attributes:
        comentario: a resposta mapeada para o contrato.
        reply_to_id: id do usuário respondido, quando a API informar.
        reply_to_usuario: nome do usuário respondido, quando a API informar.
    """

    comentario: Comment
    reply_to_id: str | None
    reply_to_usuario: str | None


@dataclass(frozen=True)
class SubCommentPage:
    """Uma página de respostas de um comentário raiz.

    Attributes:
        comments: respostas já mapeadas.
        next_cursor: cursor para a próxima página.
    """

    comments: list[SubComment]
    next_cursor: Cursor


class SearchApiPort(Protocol):
    """Busca de postagens por palavra-chave na API web do Kwai.

    Existe como *seam* de I/O: o caso de uso de busca depende desta porta, não
    do adapter HTTP, e por isso fica testável sem rede.
    """

    def search_posts(self, keyword: str, count: int, *, collected_at: IsoTimestamp) -> list[Post]:
        """Busca postagens de uma palavra-chave (uma requisição por chamada)."""
        ...


@dataclass(frozen=True)
class ProfilePage:
    """Uma página do feed de perfil devolvida pela API móvel.

    Attributes:
        posts: postagens já mapeadas para o contrato.
        next_cursor: cursor para a próxima página.
    """

    posts: list[Post]
    next_cursor: Cursor


class ProfileApiPort(Protocol):
    """Leitura das postagens de um perfil na API móvel anônima.

    São dois passos: resolver o handle para o id numérico (o feed não aceita
    handle) e então paginar o feed. O adapter busca **uma** página por chamada;
    decidir o fim da paginação é do caso de uso (via :meth:`Cursor.is_end`).
    """

    def resolve_user(self, handle: Handle) -> UserId:
        """Resolve o handle para o id numérico usado pelo feed (que não aceita handle)."""
        ...

    def fetch_profile_page(
        self,
        user_id: UserId,
        *,
        cursor: Cursor,
        count: int,
        collected_at: IsoTimestamp,
    ) -> ProfilePage:
        """Busca uma página do feed do usuário."""
        ...


class CommentApiPort(Protocol):
    """Leitura da API móvel anônima de comentários (raízes e respostas).

    O adapter busca **uma** página por chamada; decidir o fim da paginação é
    responsabilidade do caso de uso (via :meth:`Cursor.is_end`), mantendo essa
    regra fora da camada de rede.
    """

    def fetch_page(
        self,
        photo_id: PhotoId,
        *,
        cursor: Cursor,
        count: int,
        postagem_url: str,
        collected_at: IsoTimestamp,
    ) -> CommentPage:
        """Busca uma página de comentários de raiz da postagem."""
        ...

    def fetch_sub_page(
        self,
        photo_id: PhotoId,
        *,
        root_comment_id: CommentId,
        cursor: Cursor,
        count: int,
        postagem_url: str,
        collected_at: IsoTimestamp,
    ) -> SubCommentPage:
        """Busca uma página de respostas de um comentário raiz."""
        ...

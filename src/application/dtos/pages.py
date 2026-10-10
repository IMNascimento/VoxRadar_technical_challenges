"""Páginas devolvidas pelas portas de leitura: itens já mapeados e o próximo cursor.

O adapter busca **uma** página por chamada; decidir o fim da paginação é
responsabilidade do caso de uso, via a regra de paginação do domínio.
"""

from __future__ import annotations

from dataclasses import dataclass

from ...domain.entities.comment import Comment
from ...domain.entities.post import Post
from ...domain.value_objects.cursor import Cursor


@dataclass(frozen=True)
class SearchPage:
    """Uma página da busca web de uma palavra-chave.

    A busca pagina por deslocamento: não há cursor de continuação na resposta.

    Attributes:
        posts: postagens já mapeadas para o contrato.
        next_offset: deslocamento (``pcursor``) da próxima página.
    """

    posts: list[Post]
    next_offset: int


@dataclass(frozen=True)
class ProfilePage:
    """Uma página do feed de perfil devolvida pela API móvel.

    Attributes:
        posts: postagens já mapeadas para o contrato.
        next_cursor: cursor para a próxima página.
    """

    posts: list[Post]
    next_cursor: Cursor


@dataclass(frozen=True)
class RootComment:
    """Um comentário de raiz e o total de respostas que a API declara.

    Attributes:
        comment: comentário raiz já mapeado para o contrato.
        declared_replies: valor de ``sub_comment_count`` informado pela API,
            ou ``None`` quando ausente. É o total **declarado**, que pode
            diferir do que a coleta entrega.
    """

    comment: Comment
    declared_replies: int | None


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
        comment: a resposta mapeada para o contrato.
        reply_to_id: id do usuário respondido, quando a API informar.
        reply_to_usuario: nome do usuário respondido, quando a API informar.
    """

    comment: Comment
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

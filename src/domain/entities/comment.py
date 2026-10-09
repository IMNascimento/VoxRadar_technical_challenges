"""Comentário do Kwai, no formato do contrato de saída (schema ``Comentario``)."""

from __future__ import annotations

from dataclasses import dataclass, field, fields


@dataclass(frozen=True, kw_only=True)
class CommentAuthor:
    """Autor de um comentário, como a API informa; campos ausentes ficam ``None``."""

    usuario: str | None = None
    id: str | None = None


@dataclass(frozen=True, kw_only=True)
class Comment:
    """Comentário de uma postagem, no formato do schema ``Comentario``.

    Campos obrigatórios: ``postagem_url``, ``texto`` e ``coletado_em``. Propriedades
    não entram em ``dataclasses.asdict``: ``dedup_key`` não altera o contrato de saída.
    """

    id: str | None = None
    postagem_url: str
    autor: CommentAuthor = field(default_factory=CommentAuthor)
    texto: str
    curtidas: int | None = None
    data: str | None = None
    coletado_em: str

    @property
    def dedup_key(self) -> str:
        """Identidade na deduplicação: ``id`` ou ``autor``/``texto`` sem ambiguidade.

        Sem ``id``, o autor é prefixado pelo próprio comprimento antes do texto, o
        que torna a chave injetiva: pares ambíguos (ex.: autor ``a:b`` com texto
        ``c`` vs. autor ``a`` com texto ``b:c``) não colidem.
        """
        author = self.autor.id or ""
        return self.id or f"{len(author)}:{author}{self.texto}"


@dataclass(frozen=True, kw_only=True)
class ExpandedComment(Comment):
    """Comentário com o vínculo de resposta e o total declarado de respostas.

    Versão **opt-in** da coleta de comentários: raízes e respostas vêm
    numa lista plana e cada resposta aponta para a raiz via ``parent_id``. Não
    substitui o contrato oficial :class:`Comment`, que permanece inalterado
    quando a coleta não pede respostas.

    Attributes:
        parent_id: id da raiz quando o item é uma resposta; ``None`` na raiz.
        reply_to_id: id do usuário respondido, quando houver.
        reply_to_usuario: nome do usuário respondido, quando houver.
        respostas_total: total de respostas **declarado** pela API (só na raiz);
            pode ser maior que o número de respostas efetivamente coletadas.
    """

    parent_id: str | None = None
    reply_to_id: str | None = None
    reply_to_usuario: str | None = None
    respostas_total: int | None = None

    @classmethod
    def from_comment(
        cls,
        comment: Comment,
        *,
        parent_id: str | None = None,
        reply_to_id: str | None = None,
        reply_to_usuario: str | None = None,
        respostas_total: int | None = None,
    ) -> ExpandedComment:
        """Estende um comentário do contrato oficial com o vínculo de resposta."""
        base = {item.name: getattr(comment, item.name) for item in fields(Comment)}
        return cls(
            **base,
            parent_id=parent_id,
            reply_to_id=reply_to_id,
            reply_to_usuario=reply_to_usuario,
            respostas_total=respostas_total,
        )

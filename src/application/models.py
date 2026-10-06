"""Modelos de dados que validam o contrato de saída (schemas VoxRadar).

Referência: ``schemas.md`` do desafio. Os modelos garantem que a saída
JSON seja sempre aderente ao contrato, independentemente da fonte dos dados.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class AutorPostagem(BaseModel):
    """Autor de uma postagem."""

    model_config = ConfigDict(extra="forbid")

    usuario: str | None = None
    id: str | None = None
    url_perfil: str | None = None


class Engajamento(BaseModel):
    """Métricas de engajamento de uma postagem.

    Campos ausentes ficam ``None`` (desconhecido), conforme o schema: só usamos
    ``0`` quando temos certeza de que o valor é zero.
    """

    model_config = ConfigDict(extra="forbid")

    curtidas: int | None = None
    comentarios: int | None = None
    compartilhamentos: int | None = None
    visualizacoes: int | None = None


class Postagem(BaseModel):
    """Uma postagem do Kwai. Campos obrigatórios: ``url``, ``engajamento``,
    ``coletado_em``."""

    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    url: str
    autor: AutorPostagem = Field(default_factory=AutorPostagem)
    texto: str | None = None
    data_publicacao: str | None = None
    engajamento: Engajamento
    coletado_em: str


class AutorComentario(BaseModel):
    """Autor de um comentário."""

    model_config = ConfigDict(extra="forbid")

    usuario: str | None = None
    id: str | None = None


class Comentario(BaseModel):
    """Um comentário de uma postagem. Campos obrigatórios: ``postagem_url``,
    ``texto``, ``coletado_em``."""

    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    postagem_url: str
    autor: AutorComentario = Field(default_factory=AutorComentario)
    texto: str
    curtidas: int | None = None
    data: str | None = None
    coletado_em: str


class ComentarioExpandido(Comentario):
    """Comentário com o vínculo de resposta e o total declarado de respostas.

    Saída **opt-in** (``comentarios --com-respostas``): raízes e respostas vêm
    numa lista plana e cada resposta aponta para a raiz via ``parent_id``. Não
    substitui o contrato oficial :class:`Comentario`, que permanece inalterado
    quando a coleta não pede respostas.

    Attributes:
        parent_id: id da raiz quando o item é uma resposta; ``None`` na raiz.
        reply_to_id: id do usuário respondido, quando houver.
        reply_to_usuario: nome do usuário respondido, quando houver.
        respostas_total: total de respostas **declarado** pela API (só na raiz);
            pode ser maior que o número de respostas efetivamente coletadas.
    """

    model_config = ConfigDict(extra="forbid")

    parent_id: str | None = None
    reply_to_id: str | None = None
    reply_to_usuario: str | None = None
    respostas_total: int | None = None

"""Postagem do Kwai, no formato do contrato de saída (schema ``Postagem``)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, kw_only=True)
class PostAuthor:
    """Autor de uma postagem."""

    usuario: str | None = None
    id: str | None = None
    url_perfil: str | None = None


@dataclass(frozen=True, kw_only=True)
class Engagement:
    """Métricas de engajamento de uma postagem.

    Campos ausentes ficam ``None`` (desconhecido), conforme o schema: só usamos
    ``0`` quando temos certeza de que o valor é zero.
    """

    curtidas: int | None = None
    comentarios: int | None = None
    compartilhamentos: int | None = None
    visualizacoes: int | None = None


@dataclass(frozen=True, kw_only=True)
class Post:
    """Uma postagem do Kwai. Campos obrigatórios: ``url``, ``engajamento``,
    ``coletado_em``."""

    id: str | None = None
    url: str
    autor: PostAuthor = field(default_factory=PostAuthor)
    texto: str | None = None
    data_publicacao: str | None = None
    engajamento: Engagement
    coletado_em: str

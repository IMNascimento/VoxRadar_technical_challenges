"""A1_Radar."""

from datetime import datetime

from pydantic import BaseModel


class Autor(BaseModel):
    usuario: str | None = None
    id: str | None = None
    url_perfil: str | None = None


class Engajamento(BaseModel):
    curtidas: int | None = None
    comentarios: int | None = None
    compartilhamentos: int | None = None
    visualizacoes: int | None = None


class Postagem(BaseModel):
    id: str | None = None
    url: str
    autor: Autor
    texto: str | None = None
    data_publicacao: datetime | None = None
    engajamento: Engajamento
    coletado_em: datetime

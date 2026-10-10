"""A1_Radar."""

from datetime import datetime

from pydantic import BaseModel


class AutorComentario(BaseModel):
    usuario: str | None = None
    id: str | None = None


class Comentario(BaseModel):
    id: str | None = None
    postagem_url: str
    autor: AutorComentario
    texto: str
    curtidas: int | None = None
    data: datetime | None = None
    coletado_em: datetime

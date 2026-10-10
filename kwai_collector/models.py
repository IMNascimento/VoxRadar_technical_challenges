from pydantic import BaseModel, Field

# datas sempre em UTC, ex: 2026-07-27T14:30:00Z
ISO_DATE = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"


class PostAuthor(BaseModel):
    usuario: str | None = None
    id: str | None = None
    url_perfil: str | None = None


class Engagement(BaseModel):
    # None indica que a API não informou a contagem
    curtidas: int | None = None
    comentarios: int | None = None
    compartilhamentos: int | None = None
    visualizacoes: int | None = None


class Post(BaseModel):
    id: str | None = None
    url: str
    autor: PostAuthor
    texto: str | None = None
    data_publicacao: str | None = Field(default=None, pattern=ISO_DATE)
    engajamento: Engagement
    coletado_em: str = Field(pattern=ISO_DATE)


class CommentAuthor(BaseModel):
    usuario: str | None = None
    id: str | None = None


class Comment(BaseModel):
    id: str | None = None
    postagem_url: str
    autor: CommentAuthor
    texto: str
    curtidas: int | None = None
    data: str | None = Field(default=None, pattern=ISO_DATE)
    coletado_em: str = Field(pattern=ISO_DATE)


class CommentWithReplies(Comment):
    # usado no --with-replies: raízes e respostas na mesma lista
    parent_id: str | None = None  # id da raiz, quando é resposta
    reply_to_id: str | None = None
    reply_to_usuario: str | None = None
    respostas_total: int | None = None  # total que a api diz ter (só na raiz)

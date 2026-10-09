"""Referência a uma postagem: a URL informada, o id e o dono extraídos dela."""

from __future__ import annotations

from dataclasses import dataclass

from .identifiers import PhotoId


@dataclass(frozen=True)
class PostReference:
    """Postagem alvo de uma coleta de comentários, já validada.

    Construída a partir da URL por :func:`parse_post_reference`, que extrai o id
    e o dono.

    Attributes:
        photo_id: id numérico da postagem.
        url: URL informada.
        owner: handle do segmento ``@perfil`` da URL, quando houver.
    """

    photo_id: PhotoId
    url: str
    owner: str | None = None

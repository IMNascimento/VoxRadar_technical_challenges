"""Formato das URLs públicas do Kwai: única fonte do padrão de postagem e de perfil.

A URL é identidade de domínio (a deduplicação de postagens cai para ela quando
falta o id), então montar e interpretar URLs fica aqui, e não em cada camada.
"""

from __future__ import annotations

import re
from urllib.parse import unquote, urlsplit

from ..entities.post import Post
from ..exceptions.domain_exceptions import InvalidInputError, InvalidValueError
from ..value_objects.identifiers import PhotoId
from ..value_objects.post_reference import PostReference

# Origem web do Kwai: base das URLs canônicas de postagem e de perfil.
BASE_URL: str = "https://www.kwai.com"

_PHOTO_ID_RE = re.compile(r"/(?:video|photo)/(\d+)")


def profile_url(handle: str) -> str:
    """URL canônica de um perfil: ``/@{handle}``."""
    return f"{BASE_URL}/@{handle}"


def post_url(handle: str, photo_id: str) -> str:
    """URL canônica de uma postagem: ``/@{handle}/video/{photo_id}``."""
    return f"{profile_url(handle)}/video/{photo_id}"


def extract_photo_id(url: str) -> PhotoId:
    """Extrai o id numérico de uma URL de postagem.

    Args:
        url: link ``.../@perfil/video/<id>`` ou ``.../photo/<id>``.

    Returns:
        O :class:`PhotoId` da postagem.

    Raises:
        InvalidInputError: se a URL não casar com o padrão esperado.
    """
    match = _PHOTO_ID_RE.search(url or "")
    if not match:
        raise InvalidInputError(
            f"URL de postagem inválida: {url!r} "
            "(esperado .../@perfil/video/<id> ou .../photo/<id>)"
        )
    return PhotoId(match.group(1))


def parse_post_reference(url: str) -> PostReference:
    """Valida a URL de uma postagem e a referencia pelo id e pelo dono extraídos.

    Raises:
        InvalidInputError: se a URL não casar com o padrão esperado.
    """
    return PostReference(extract_photo_id(url), url, owner=_extract_owner(url))


def reference_post(post: Post) -> PostReference:
    """Referencia uma postagem já coletada pelo id dela, sem reinterpretar a URL.

    Raises:
        InvalidValueError: se a postagem vier da API sem id numérico.
    """
    if post.id is None:
        raise InvalidValueError(f"postagem sem id: {post.url!r}")
    return PostReference(PhotoId(post.id), post.url, owner=_extract_owner(post.url))


def _extract_owner(url: str) -> str | None:
    """Handle do segmento ``@perfil`` da URL, quando houver."""
    for part in urlsplit(url).path.split("/"):
        if part.startswith("@") and len(part) > 1:
            return unquote(part[1:])
    return None

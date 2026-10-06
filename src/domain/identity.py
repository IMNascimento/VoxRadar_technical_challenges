"""Identificadores e chaves de deduplicação dos dados do Kwai."""

from __future__ import annotations

import re

from .exceptions import InvalidInputError
from .value_objects.identifiers import Handle, PhotoId

_PHOTO_ID_RE = re.compile(r"/(?:video|photo)/(\d+)")


def normalize_handle(user: str) -> Handle:
    """Remove ``@``/espaços das bordas e valida a conta informada.

    Args:
        user: conta do usuário (ex.: ``@perfil`` ou ``perfil``).

    Returns:
        O :class:`Handle` validado, sem ``@`` e sem espaços nas bordas.

    Raises:
        InvalidInputError: se a conta ficar vazia ou contiver ``/`` ou espaço.
    """
    handle = user.strip().lstrip("@").strip()
    if not handle:
        raise InvalidInputError("usuário inválido")
    return Handle(handle)


def extract_photo_id(post_url: str) -> PhotoId:
    """Extrai o id numérico de uma URL de postagem.

    Args:
        post_url: link ``.../@perfil/video/<id>`` ou ``.../photo/<id>``.

    Returns:
        O :class:`PhotoId` da postagem.

    Raises:
        InvalidInputError: se a URL não casar com o padrão esperado.
    """
    match = _PHOTO_ID_RE.search(post_url or "")
    if not match:
        raise InvalidInputError(
            f"URL de postagem inválida: {post_url!r} "
            "(esperado .../@perfil/video/<id> ou .../photo/<id>)"
        )
    return PhotoId(match.group(1))


def post_dedup_key(post_id: str | None, url: str) -> str:
    """Chave de deduplicação de postagem: ``id`` quando houver, senão ``url``."""
    return post_id or url


def comment_dedup_key(comment_id: str | None, author_id: str | None, text: str) -> str:
    """Chave de deduplicação de comentário: ``id`` ou ``autor``/``texto`` sem ambiguidade.

    Sem ``id``, o autor é prefixado pelo próprio comprimento antes do texto, o
    que torna a chave injetiva: pares ambíguos (ex.: autor ``a:b`` com texto
    ``c`` vs. autor ``a`` com texto ``b:c``) não colidem.
    """
    author = "" if author_id is None else author_id
    return comment_id or f"{len(author)}:{author}{text}"

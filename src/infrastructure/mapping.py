"""Mapeamento dos dados crus do Kwai para os modelos de contrato.

Isola o conhecimento do formato interno do Kwai (nomes de campos, timestamps,
construção de URLs) das demais camadas.
"""

from __future__ import annotations

import html
from typing import Any

from ..application.models import (
    AutorComentario,
    AutorPostagem,
    Comentario,
    Engajamento,
    Postagem,
)
from ..application.ports import SubComment
from ..domain.constants import BASE_URL
from ..shared.utils.coercion import as_int_scalar
from ..shared.utils.timestamps import iso_from_timestamp_ms
from .exceptions import UnexpectedResponseError


def _first(data: dict[str, Any], *keys: str) -> Any:
    """Retorna o primeiro valor não-``None`` dentre as chaves informadas."""
    for key in keys:
        value = data.get(key)
        if value is not None:
            return value
    return None


def _as_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _clean_text(value: Any) -> str | None:
    text = _as_str(value)
    return html.unescape(text) if text is not None else None


def build_post_url(handle: str | None, photo_id: str | None) -> str | None:
    """Monta a URL canônica de uma postagem: ``/@{handle}/video/{photo_id}``."""
    if not handle or not photo_id:
        return None
    return f"{BASE_URL}/@{handle}/video/{photo_id}"


def _build_post_author(feed: dict[str, Any], *, handle: str | None) -> AutorPostagem:
    """Monta o autor preservando os fallbacks de nome/id do feed."""
    usuario = f"@{feed['kwai_id']}" if feed.get("kwai_id") else _as_str(feed.get("user_name"))
    return AutorPostagem(
        usuario=usuario,
        id=_as_str(_first(feed, "user_id_str", "user_id")),
        url_perfil=f"{BASE_URL}/@{handle}" if handle else None,
    )


def _build_engagement(feed: dict[str, Any]) -> Engajamento:
    """Extrai as métricas do feed; ausente vira ``None`` (nunca ``0``)."""
    return Engajamento(
        curtidas=as_int_scalar(feed.get("like_count")),
        comentarios=as_int_scalar(feed.get("comment_count")),
        compartilhamentos=as_int_scalar(feed.get("forward_count")),
        visualizacoes=as_int_scalar(feed.get("view_count")),
    )


def parse_feed(feed: dict[str, Any], *, collected_at: str) -> Postagem:
    """Converte um item de feed do Kwai em :class:`Postagem`.

    Usado tanto na busca por palavra-chave quanto nas postagens de usuário, que
    compartilham o mesmo formato de feed.

    Args:
        feed: item cru da lista ``feeds``.
        collected_at: carimbo de coleta aplicado à postagem.

    Returns:
        A postagem aderente ao contrato.

    Raises:
        UnexpectedResponseError: se o feed não permitir montar a URL da postagem
            (``photo_id`` ou ``handle`` ausente).
    """
    photo_id = _as_str(_first(feed, "photo_id_str", "photo_id"))
    handle = _as_str(_first(feed, "kwai_id", "user_id_str"))
    url = build_post_url(handle, photo_id)
    if url is None:
        raise UnexpectedResponseError(
            "feed sem photo_id/handle: impossível montar a URL da postagem"
        )
    return Postagem(
        id=photo_id,
        url=url,
        autor=_build_post_author(feed, handle=handle),
        texto=_clean_text(_first(feed, "caption", "user_text")),
        data_publicacao=iso_from_timestamp_ms(feed.get("timestamp")),
        engajamento=_build_engagement(feed),
        coletado_em=collected_at,
    )


def parse_comment(raw: dict[str, Any], *, postagem_url: str, collected_at: str) -> Comentario:
    """Converte um comentário cru do Kwai em :class:`Comentario`.

    Args:
        raw: comentário cru da lista ``rootComments``.
        postagem_url: URL da postagem à qual o comentário pertence.
        collected_at: carimbo de coleta aplicado ao comentário.

    Returns:
        O comentário aderente ao contrato.
    """
    return Comentario(
        id=_as_str(_first(raw, "comment_id", "id")),
        postagem_url=postagem_url,
        autor=AutorComentario(
            usuario=_as_str(raw.get("author_name")),
            id=_as_str(raw.get("author_id")),
        ),
        texto=_clean_text(raw.get("content")) or "",
        curtidas=as_int_scalar(raw.get("liked_count")),
        data=iso_from_timestamp_ms(raw.get("timestamp")),
        coletado_em=collected_at,
    )


def parse_sub_comment(raw: dict[str, Any], *, postagem_url: str, collected_at: str) -> SubComment:
    """Converte uma resposta crua do Kwai em :class:`SubComment`.

    Args:
        raw: resposta crua da lista ``subComments``.
        postagem_url: URL da postagem à qual a resposta pertence.
        collected_at: carimbo de coleta aplicado à resposta.

    Returns:
        A resposta com o comentário mapeado e o vínculo a quem foi respondido.
    """
    reply_to_id = _as_str(raw.get("reply_to"))
    if reply_to_id == "0":
        reply_to_id = None
    return SubComment(
        comentario=parse_comment(raw, postagem_url=postagem_url, collected_at=collected_at),
        reply_to_id=reply_to_id,
        reply_to_usuario=_as_str(raw.get("replyToUserName")),
    )

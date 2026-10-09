"""Mapeamento dos dados crus do Kwai para as entidades do contrato.

Isola o conhecimento do formato interno do Kwai (nomes de campos e timestamps)
das demais camadas; o formato das URLs públicas vem de
:mod:`src.domain.services.post_urls`.
"""

from __future__ import annotations

import html
from typing import Any

from ...application.dtos.pages import SubComment
from ...domain.entities.comment import Comment, CommentAuthor
from ...domain.entities.post import Engagement, Post, PostAuthor
from ...domain.services.post_urls import post_url, profile_url
from ...shared.logging.logging_config import get_logger
from .coercion import as_int_scalar, iso_from_timestamp_ms
from .exceptions import UnexpectedResponseError

logger = get_logger("mapping")


def _get_first_present_value(data: dict[str, Any], *keys: str) -> Any:
    """Retorna o primeiro valor não-``None`` dentre as chaves informadas."""
    for key in keys:
        value = data.get(key)
        if value is not None:
            return value
    return None


def _normalize_optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _clean_text(value: Any) -> str | None:
    text = _normalize_optional_string(value)
    return html.unescape(text) if text is not None else None


def _build_post_author(feed: dict[str, Any], *, handle: str | None) -> PostAuthor:
    """Monta o autor preservando os fallbacks de nome/id do feed."""
    usuario = (
        f"@{feed['kwai_id']}"
        if feed.get("kwai_id")
        else _normalize_optional_string(feed.get("user_name"))
    )
    return PostAuthor(
        usuario=usuario,
        id=_normalize_optional_string(_get_first_present_value(feed, "user_id_str", "user_id")),
        url_perfil=profile_url(handle) if handle else None,
    )


def _build_engagement(feed: dict[str, Any]) -> Engagement:
    """Extrai as métricas do feed; ausente vira ``None`` (nunca ``0``)."""
    return Engagement(
        curtidas=as_int_scalar(feed.get("like_count")),
        comentarios=as_int_scalar(feed.get("comment_count")),
        compartilhamentos=as_int_scalar(feed.get("forward_count")),
        visualizacoes=as_int_scalar(feed.get("view_count")),
    )


def parse_feed(feed: dict[str, Any], *, collected_at: str) -> Post:
    """Converte um item de feed do Kwai em :class:`Post`.

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
    photo_id = _normalize_optional_string(
        _get_first_present_value(feed, "photo_id_str", "photo_id")
    )
    handle = _normalize_optional_string(_get_first_present_value(feed, "kwai_id", "user_id_str"))
    if not handle or not photo_id:
        raise UnexpectedResponseError(
            "feed sem photo_id/handle: impossível montar a URL da postagem"
        )
    return Post(
        id=photo_id,
        url=post_url(handle, photo_id),
        autor=_build_post_author(feed, handle=handle),
        texto=_clean_text(_get_first_present_value(feed, "caption", "user_text")),
        data_publicacao=iso_from_timestamp_ms(feed.get("timestamp")),
        engajamento=_build_engagement(feed),
        coletado_em=collected_at,
    )


def parse_feeds(feeds: Any, *, collected_at: str) -> list[Post]:
    """Mapeia uma lista de feeds; itens inválidos são ignorados com aviso.

    Um feed órfão (sem ``photo_id`` ou sem handle) não derruba o lote: ele é
    registrado no log e os demais seguem.

    Args:
        feeds: lista crua de feeds (``None``/ausente vira lista vazia).
        collected_at: carimbo de coleta aplicado a cada postagem.

    Returns:
        As postagens mapeadas, na ordem do lote.
    """
    if feeds is None:
        return []
    if not isinstance(feeds, list):
        raise UnexpectedResponseError("feeds deve ser uma lista JSON")
    posts: list[Post] = []
    for index, feed in enumerate(feeds):
        if not isinstance(feed, dict):
            logger.warning("feed ignorado: feeds[%d] não é um objeto JSON", index)
            continue
        try:
            posts.append(parse_feed(feed, collected_at=collected_at))
        except UnexpectedResponseError as exc:
            logger.warning("feed ignorado: %s", exc)
    return posts


def parse_comment(raw: dict[str, Any], *, post_url: str, collected_at: str) -> Comment:
    """Converte um comentário cru do Kwai em :class:`Comment`.

    Args:
        raw: comentário cru da lista ``rootComments``.
        post_url: URL da postagem à qual o comentário pertence.
        collected_at: carimbo de coleta aplicado ao comentário.

    Returns:
        O comentário aderente ao contrato.
    """
    return Comment(
        id=_normalize_optional_string(_get_first_present_value(raw, "comment_id", "id")),
        postagem_url=post_url,
        autor=CommentAuthor(
            usuario=_normalize_optional_string(raw.get("author_name")),
            id=_normalize_optional_string(raw.get("author_id")),
        ),
        texto=_clean_text(raw.get("content")) or "",
        curtidas=as_int_scalar(raw.get("liked_count")),
        data=iso_from_timestamp_ms(raw.get("timestamp")),
        coletado_em=collected_at,
    )


def parse_sub_comment(raw: dict[str, Any], *, post_url: str, collected_at: str) -> SubComment:
    """Converte uma resposta crua do Kwai em :class:`SubComment`.

    Args:
        raw: resposta crua da lista ``subComments``.
        post_url: URL da postagem à qual a resposta pertence.
        collected_at: carimbo de coleta aplicado à resposta.

    Returns:
        A resposta com o comentário mapeado e o vínculo a quem foi respondido.
    """
    reply_to_id = _normalize_optional_string(raw.get("reply_to"))
    if reply_to_id == "0":
        reply_to_id = None
    return SubComment(
        comment=parse_comment(raw, post_url=post_url, collected_at=collected_at),
        reply_to_id=reply_to_id,
        reply_to_usuario=_normalize_optional_string(raw.get("replyToUserName")),
    )

import html
import logging
from datetime import UTC, datetime
from typing import Any

from kwai_collector.models import Comment, CommentAuthor, Engagement, Post, PostAuthor

log = logging.getLogger(__name__)

BASE_URL = "https://www.kwai.com"
DATE_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def now_iso() -> str:
    return datetime.now(UTC).strftime(DATE_FORMAT)


def to_int(value: Any) -> int | None:
    # campo que não veio fica None, nunca 0
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def ms_to_iso(value: Any) -> str | None:
    ms = to_int(value)
    if not ms or ms <= 0:
        return None
    try:
        return datetime.fromtimestamp(ms / 1000, tz=UTC).strftime(DATE_FORMAT)
    except (OverflowError, OSError, ValueError):
        return None


def get_first_value(data: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if data.get(key) is not None:
            return data[key]
    return None


def clean_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def clean_text(value: Any) -> str | None:
    text = clean_string(value)
    return html.unescape(text) if text else None


def parse_post(feed: dict[str, Any], collected_at: str) -> Post | None:
    photo_id = clean_string(get_first_value(feed, "photo_id_str", "photo_id"))
    handle = clean_string(get_first_value(feed, "kwai_id", "user_id_str"))
    if not photo_id or not handle:
        return None  # sem isso não tem como montar a url do post

    usuario: str | None
    if feed.get("kwai_id"):
        usuario = "@" + str(feed["kwai_id"])
    else:
        usuario = clean_string(feed.get("user_name"))

    return Post(
        id=photo_id,
        url=f"{BASE_URL}/@{handle}/video/{photo_id}",
        autor=PostAuthor(
            usuario=usuario,
            id=clean_string(get_first_value(feed, "user_id_str", "user_id")),
            url_perfil=f"{BASE_URL}/@{handle}",
        ),
        texto=clean_text(get_first_value(feed, "caption", "user_text")),
        data_publicacao=ms_to_iso(feed.get("timestamp")),
        engajamento=Engagement(
            curtidas=to_int(feed.get("like_count")),
            comentarios=to_int(feed.get("comment_count")),
            compartilhamentos=to_int(feed.get("forward_count")),
            visualizacoes=to_int(feed.get("view_count")),
        ),
        coletado_em=collected_at,
    )


def parse_posts(feeds: Any, collected_at: str) -> list[Post]:
    posts = []
    for feed in feeds or []:
        if not isinstance(feed, dict):
            continue
        post = parse_post(feed, collected_at)
        if post is None:
            log.warning("post ignorado: veio sem photo_id ou usuário")
            continue
        posts.append(post)
    return posts


def parse_comment(raw: dict[str, Any], post_url: str, collected_at: str) -> Comment:
    return Comment(
        id=clean_string(get_first_value(raw, "comment_id", "id")),
        postagem_url=post_url,
        autor=CommentAuthor(
            usuario=clean_string(raw.get("author_name")),
            id=clean_string(raw.get("author_id")),
        ),
        texto=clean_text(raw.get("content")) or "",
        curtidas=to_int(raw.get("liked_count")),
        data=ms_to_iso(raw.get("timestamp")),
        coletado_em=collected_at,
    )

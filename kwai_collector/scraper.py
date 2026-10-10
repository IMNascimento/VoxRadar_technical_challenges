import logging
import re
from typing import Any

from kwai_collector import client
from kwai_collector.models import Comment, CommentWithReplies, Post
from kwai_collector.parser import clean_string, now_iso, parse_comment, parse_posts, to_int

log = logging.getLogger(__name__)

SEARCH_PATH = "/rest/o/w/pwa/v2/search/word/outer"
USER_INFO_PATH = "/rest/o/user/getInfo"
PROFILE_PATH = "/rest/o/feed/profile"
COMMENTS_PATH = "/rest/o/comment/list/v2"
REPLIES_PATH = "/rest/o/comment/sublist"

SEARCH_PAGE_SIZE = 50  # itens por página da busca; o pcursor avança nesse passo
END_CURSORS = ["", "no_more", "nomore", "-1", "0"]


class InvalidInput(Exception):
    pass


def next_cursor(data: dict[str, Any], seen: set[str]) -> str | None:
    # None encerra a paginação, inclusive quando o cursor se repete
    cursor = str(data.get("pcursor") or "")
    if cursor in END_CURSORS:
        return None
    if cursor in seen:
        log.warning("cursor repetido (%s), parando a paginação", cursor)
        return None
    seen.add(cursor)
    return cursor


def comment_key(comment: Comment) -> str:
    # comentário sem id usa autor + texto pra não duplicar
    return comment.id or f"{comment.autor.id}|{comment.texto}"


def search_posts(keywords: list[str], limit: int = 20) -> list[Post]:
    keywords = [k.strip() for k in keywords if k.strip()]
    if not keywords:
        raise InvalidInput("informe pelo menos uma palavra-chave")

    collected_at = now_iso()
    count = min(limit, SEARCH_PAGE_SIZE)
    posts: list[Post] = []
    seen: set[str | None] = set()
    for keyword in keywords:
        log.info("buscando %r", keyword)
        offset = 0
        while len(posts) < limit:
            payload = {
                "searchWord": keyword,
                "count": count,
                "fromUser": False,
                "mobile": True,
                "pcursor": offset,
                "request_source": 1102,
                "url": client.WEB_URL + "/discover",
            }
            data = client.post_web(SEARCH_PATH, payload)
            new = 0
            for post in parse_posts(data.get("feeds"), collected_at):
                if post.id not in seen:
                    seen.add(post.id)
                    posts.append(post)
                    new += 1
            # quando a palavra se esgota, a API repete itens em vez de devolver lista vazia
            if not new:
                break
            offset += count
        if len(posts) >= limit:
            break

    log.info("busca terminou com %d posts", len(posts[:limit]))
    return posts[:limit]


def get_user_id(handle: str) -> str:
    # o feed do perfil precisa do id numérico do usuário
    body = {"userIds": "@" + handle, "client_key": client.CLIENT_KEY, "os": "android"}
    data = client.post_mobile(USER_INFO_PATH, client.build_app_query(), body)
    users = data.get("users") or []
    user_id = str(users[0].get("user_id") or "") if users else ""
    if not user_id.isdigit():
        raise client.KwaiError(f"usuário @{handle} não encontrado")
    return user_id


def get_user_posts(user: str, limit: int | None = None) -> list[Post]:
    handle = user.strip().lstrip("@").strip()
    if not handle or " " in handle or "/" in handle or "@" in handle:
        raise InvalidInput(f"usuário inválido: {user!r}")

    log.info("coletando posts de @%s", handle)
    collected_at = now_iso()
    user_id = get_user_id(handle)
    # parâmetros usados para consultar o feed do perfil
    query = {"kpn": "KWAI", "appver": client.APP_VERSION}

    posts: list[Post] = []
    seen: set[str | None] = set()
    seen_cursors: set[str] = set()
    cursor: str | None = ""
    while cursor is not None:
        body = {
            "user_id": user_id,
            "count": "30",
            "privacy": "public",
            "lang": "en",
            "pcursor": cursor,
            "client_key": client.CLIENT_KEY,
            "os": "android",
        }
        data = client.post_mobile(PROFILE_PATH, query, body)
        page = parse_posts(data.get("feeds"), collected_at)
        for post in page:
            if post.id in seen:
                continue
            seen.add(post.id)
            posts.append(post)
            if limit and len(posts) >= limit:
                return posts
        cursor = next_cursor(data, seen_cursors) if page else None

    log.info("@%s: %d posts coletados", handle, len(posts))
    return posts


def get_photo_id(url: str) -> str:
    match = re.search(r"/(?:video|photo)/(\d+)", url or "")
    if not match:
        raise InvalidInput(f"URL inválida: {url!r} (esperado .../@perfil/video/<id>)")
    return match.group(1)


def get_root_comments(
    photo_id: str, post_url: str, collected_at: str, limit: int | None = None
) -> list[tuple[Comment, int | None]]:
    # cada item guarda o comentário e o total de respostas informado pela API
    comments: list[tuple[Comment, int | None]] = []
    seen: set[str] = set()
    seen_cursors: set[str] = set()
    cursor: str | None = ""
    while cursor is not None:
        body = {
            "order": "desc",
            "photoPageType": "0",
            "requestType": "3",
            "isPreload": "false",
            "preloadSource": "",
            "os": "android",
            "client_key": client.CLIENT_KEY,
            "photoId": photo_id,
            "count": "50",
            "pcursor": cursor,
        }
        data = client.post_mobile(COMMENTS_PATH, client.build_app_query(), body)
        raws = data.get("rootComments") or []
        for raw in raws:
            comment = parse_comment(raw, post_url, collected_at)
            if comment_key(comment) in seen:
                continue
            seen.add(comment_key(comment))
            comments.append((comment, to_int(raw.get("sub_comment_count"))))
            if limit and len(comments) >= limit:
                return comments
        cursor = next_cursor(data, seen_cursors) if raws else None
    return comments


def get_replies(
    photo_id: str, post_url: str, root_id: str, collected_at: str
) -> list[CommentWithReplies]:
    replies: list[CommentWithReplies] = []
    seen_cursors: set[str] = set()
    cursor: str | None = ""
    while cursor is not None:
        body = {
            "photoId": photo_id,
            "rootCommentId": root_id,
            "order": "desc",
            "pcursor": cursor,
            "count": "100",
            "client_key": client.CLIENT_KEY,
        }
        data = client.post_mobile(REPLIES_PATH, client.build_app_query(), body)
        raws = data.get("subComments") or []
        for raw in raws:
            reply_to = clean_string(raw.get("reply_to"))
            comment = parse_comment(raw, post_url, collected_at)
            reply = CommentWithReplies(
                **comment.model_dump(),
                parent_id=root_id,
                reply_to_id=None if reply_to == "0" else reply_to,
                reply_to_usuario=clean_string(raw.get("replyToUserName")),
            )
            replies.append(reply)
        cursor = next_cursor(data, seen_cursors) if raws else None
    return replies


def get_comments(
    post_url: str, limit: int | None = None, with_replies: bool = False
) -> list[Comment]:
    photo_id = get_photo_id(post_url)
    log.info("coletando comentários do post %s", photo_id)
    collected_at = now_iso()
    roots = get_root_comments(photo_id, post_url, collected_at, limit)
    if not with_replies:
        return [comment for comment, _ in roots]

    # lista plana: cada raiz seguida das respostas dela (parent_id aponta pra raiz)
    result: list[Comment] = []
    seen = {comment_key(comment) for comment, _ in roots}
    for comment, total in roots:
        result.append(CommentWithReplies(**comment.model_dump(), respostas_total=total))
        if not comment.id or not total:
            continue
        for reply in get_replies(photo_id, post_url, comment.id, collected_at):
            if comment_key(reply) not in seen:
                seen.add(comment_key(reply))
                result.append(reply)
    return result

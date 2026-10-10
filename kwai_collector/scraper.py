import logging
from typing import Any

from kwai_collector import client
from kwai_collector.models import Post
from kwai_collector.parser import now_iso, parse_posts

log = logging.getLogger(__name__)

SEARCH_PATH = "/rest/o/w/pwa/v2/search/word/outer"
USER_INFO_PATH = "/rest/o/user/getInfo"
PROFILE_PATH = "/rest/o/feed/profile"

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

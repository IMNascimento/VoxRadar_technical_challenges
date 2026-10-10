import logging

from kwai_collector import client
from kwai_collector.models import Post
from kwai_collector.parser import now_iso, parse_posts

log = logging.getLogger(__name__)

SEARCH_PATH = "/rest/o/w/pwa/v2/search/word/outer"

SEARCH_PAGE_SIZE = 50  # itens por página da busca; o pcursor avança nesse passo


class InvalidInput(Exception):
    pass


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

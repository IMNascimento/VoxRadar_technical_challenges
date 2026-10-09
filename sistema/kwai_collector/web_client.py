"""
Coleta via as rotas WEB do kwai.com (nao precisam de __NS_sig3):

- `buscar_por_palavra_chave`: POST em /rest/o/w/pwa/v2/search/word/outer,
  publico, sem necessidade de login/cookies. Paginamos incrementando
  `pcursor` no CORPO da requisicao em passos de `count`, o servidor
  nao devolve um cursor de volta, mas aceita e respeita o offset enviado
  (confirmado empiricamente: paginas consecutivas nao tem overlap).

- `carregar_perfil`: dois endpoints publicos do site, sem login/cookies:
  `/rest/o/w/pwa/profile` (bio, seguidores, etc.) e
  `/rest/o/w/pc/feed/profile` (postagens, paginadas por `cursor` ->
  `pcursor`, 20 por pagina, ate o fim do historico do perfil). 
"""
import re
from typing import List, Optional, Tuple

from curl_cffi import requests as curl_requests

from . import config
from .errors import InvalidUrlError, NetworkError
from .schemas import build_perfil, build_postagem, ms_timestamp_to_iso

SEARCH_URL = f"{config.KWAI_WEB_BASE_URL}/rest/o/w/pwa/v2/search/word/outer"

# Aceita "@usuario", "usuario" ou uma URL completa do perfil/video.
_HANDLE_RE = re.compile(r"^@?([A-Za-z0-9_.\-]+)$")
_HANDLE_FROM_URL_RE = re.compile(r"kwai\.com/@([A-Za-z0-9_.\-]+)", re.IGNORECASE)


def normalizar_handle(user: str) -> str:
    """Aceita "@usuario", "usuario" ou uma URL (perfil ou video) e
    devolve so o handle, sem "@"."""
    user = user.strip()
    match_url = _HANDLE_FROM_URL_RE.search(user)
    if match_url:
        return match_url.group(1)
    match = _HANDLE_RE.match(user)
    if not match:
        raise InvalidUrlError(f"usuario invalido: {user!r}")
    return match.group(1)


def _primeira_url(lista: Optional[list]) -> Optional[str]:
    if not lista:
        return None
    primeiro = lista[0]
    return primeiro.get("url") if isinstance(primeiro, dict) else None


def _texto_legivel(caption: Optional[str]) -> Optional[str]:
    """O Kwai usa o literal "..." como placeholder de "sem legenda" em
    alguns feeds (confirmado comparando com a pagina do video, que
    mostra a legenda real como string vazia nesses casos), Isso é tratado
    como None em vez de propagar um valor que nao e texto real."""
    if caption is None or caption == "...":
        return None
    return caption


def _feed_item_to_postagem(item: dict) -> dict:
    kwai_id = item.get("kwai_id")
    photo_id = item.get("photo_id_str") or item.get("photo_id")
    url = f"{config.KWAI_WEB_BASE_URL}/@{kwai_id}/video/{photo_id}" if kwai_id and photo_id else config.KWAI_WEB_BASE_URL
    user_id = item.get("user_id")
    data_publicacao = ms_timestamp_to_iso(item.get("timestamp"))
    return build_postagem(
        id_=str(photo_id) if photo_id is not None else None,
        url=url,
        autor_usuario=f"@{kwai_id}" if kwai_id else None,
        autor_id=str(user_id) if user_id is not None else None,
        autor_url_perfil=f"{config.KWAI_WEB_BASE_URL}/@{kwai_id}" if kwai_id else None,
        texto=_texto_legivel(item.get("caption")),
        data_publicacao=data_publicacao,
        curtidas=item.get("like_count"),
        comentarios=item.get("comment_count"),
        compartilhamentos=item.get("forward_count"),
        visualizacoes=item.get("view_count"),
        video_url=_primeira_url(item.get("main_mv_urls")),
        thumbnail_url=_primeira_url(item.get("cover_thumbnail_urls")),
    )


def buscar_por_palavra_chave(keyword: str, limit: int = 50) -> List[dict]:
    """Busca postagens publicas por palavra-chave (rota web, sem sig3)."""
    if not keyword or not keyword.strip():
        raise InvalidUrlError("palavra-chave vazia")

    headers = {
        "user-agent": config.WEB_USER_AGENT,
        "accept": "application/json, text/plain, */*",
        "content-type": "application/json",
        "referer": f"{config.KWAI_WEB_BASE_URL}/",
        "accept-language": "pt-BR",
    }

    results: List[dict] = []
    pcursor = 0
    page_size = config.SEARCH_PAGE_SIZE
    seen_ids = set()

    while len(results) < limit:
        body = {
            "ai_content": False,
            "need_ld_json": False,
            "need_tdk": False,
            "searchWord": keyword,
            "pcursor": pcursor,
            "mobile": True,
            "request_source": 1102,
            "fromUser": False,
            "seoDefaultFilterV2": True,
            "url": f"{config.KWAI_WEB_BASE_URL}/",
            "count": page_size,
        }
        try:
            resp = curl_requests.post(
                SEARCH_URL,
                json=body,
                headers=headers,
                timeout=config.HTTP_TIMEOUT_SECONDS,
                impersonate="chrome131",
            )
        except Exception as e:
            raise NetworkError(f"falha de rede ao buscar '{keyword}': {e}") from e

        if resp.status_code != 200:
            raise NetworkError(f"HTTP {resp.status_code} ao buscar '{keyword}'")

        try:
            data = resp.json()
        except Exception as e:
            raise NetworkError(f"resposta invalida (nao-JSON) ao buscar '{keyword}': {e}") from e

        if data.get("result") != 1:
            # Sem resultados ou erro reportado pelo servidor -- nao e uma
            # falha de rede, so nao ha (mais) conteudo.
            break

        feeds = data.get("feeds") or []
        if not feeds:
            break

        novo = False
        for item in feeds:
            pid = item.get("photo_id_str") or item.get("photo_id")
            if pid in seen_ids:
                continue
            seen_ids.add(pid)
            results.append(_feed_item_to_postagem(item))
            novo = True
            if len(results) >= limit:
                break

        if not novo or len(feeds) < page_size:
            break

        pcursor += page_size

    return results[:limit]


def _userprofile_to_perfil(handle: str, up: dict) -> dict:
    profile = up.get("profile") or {}
    owner_count = up.get("ownerCount") or {}
    return build_perfil(
        usuario=f"@{handle}",
        id_=str(profile.get("user_id")) if profile.get("user_id") is not None else None,
        nome=profile.get("user_name"),
        bio=profile.get("userText") or profile.get("user_text"),
        verificado=profile.get("verified"),
        avatar_url=profile.get("headurl"),
        seguidores=owner_count.get("fan"),
        seguindo=owner_count.get("follow"),
        total_postagens=owner_count.get("photo"),
        url_perfil=f"{config.KWAI_WEB_BASE_URL}/@{handle}",
    )


PROFILE_URL = f"{config.KWAI_WEB_BASE_URL}/rest/o/w/pwa/profile"
PROFILE_FEED_URL = f"{config.KWAI_WEB_BASE_URL}/rest/o/w/pc/feed/profile"


def _headers_web() -> dict:
    return {
        "user-agent": config.WEB_USER_AGENT,
        "accept": "application/json, text/plain, */*",
        "content-type": "application/json",
        "referer": f"{config.KWAI_WEB_BASE_URL}/",
        "accept-language": "pt-BR",
    }


def _post_json(url: str, body: dict, descricao: str) -> dict:
    try:
        resp = curl_requests.post(
            url,
            json=body,
            headers=_headers_web(),
            timeout=config.HTTP_TIMEOUT_SECONDS,
            impersonate="chrome131",
        )
    except Exception as e:
        raise NetworkError(f"falha de rede ao {descricao}: {e}") from e
    if resp.status_code != 200:
        raise NetworkError(f"HTTP {resp.status_code} ao {descricao}")
    try:
        return resp.json()
    except Exception as e:
        raise NetworkError(f"resposta invalida (nao-JSON) ao {descricao}: {e}") from e


def carregar_perfil(user: str, limit: int = 100) -> Tuple[Optional[dict], List[dict]]:
    """Devolve (perfil, postagens) de um usuario, sem login e sem navegador.
    `perfil` vem None se o servidor nao trouxer `userProfile` 
    (usuario inexistente/privado); nunca inventado."""
    handle = normalizar_handle(user)

    dados = _post_json(
        PROFILE_URL,
        {"userId": handle, "mcc": "", "deviceId": "", "fromPhoto": False},
        f"carregar perfil '{handle}'",
    )
    user_profile = dados.get("userProfile")
    perfil = _userprofile_to_perfil(handle, user_profile) if user_profile else None

    return perfil, _postagens_do_perfil(handle, limit)


def _postagens_do_perfil(handle: str, limit: int) -> List[dict]:
    postagens: List[dict] = []
    seen_ids = set()
    cursor = None
    while len(postagens) < limit:
        # O site manda o handle COM "@" nesta rota (ao contrario de
        # /pwa/profile, que tira o "@"). Sem ele alguns perfis vem com
        # `feeds` vazio e `cursor: "no_more"` (ex.: @luansantana).
        body = {"userId": f"@{handle}", "fromPage": "PC_PROFILE", "beforePage": "", "count": 20}
        if cursor is not None:
            body["pcursor"] = cursor
        data = _post_json(PROFILE_FEED_URL, body, f"listar postagens de '{handle}'")
        if data.get("result") != 1:
            break
        feeds = data.get("feeds") or []
        if not feeds:
            break

        novo = False
        for item in feeds:
            pid = item.get("photo_id_str") or item.get("photo_id")
            if pid in seen_ids:
                continue
            seen_ids.add(pid)
            postagens.append(_feed_item_to_postagem(item))
            novo = True
            if len(postagens) >= limit:
                break

        # `cursor` e um token opaco devolvido pelo servidor (timestamp do
        # ultimo item) -- reenviamos como `pcursor`.
        cursor = data.get("cursor")
        if not novo or cursor in (None, "", "no_more"):
            break
    return postagens[:limit]


def postagens_do_usuario(username: str, limit: int = 100) -> List[dict]:
    """Atalho que descarta o perfil (mantido para compatibilidade)."""
    return _postagens_do_perfil(normalizar_handle(username), limit)

"""
Coleta de comentarios via a rota MOBILE do app, que exige tanto `sig`
quanto `__NS_sig3`. E a rota que motivou toda a pesquisa documentada em
PESQUISA.md:

  - `sig` (MD5): reimplementado em Python puro em `kwai_sign.py`
    (ver PESQUISA.md)
  - `__NS_sig3`: calculado chamando o servico local em `server/`
    (emulacao da lib nativa `libkwsgmain.so` via unidbg/Java, SEM
    emulador Android rodando em tempo de execucao) atraves de
    `kwai_collector.sig3.assinar(...)`.

A string canonica assinada pelo `__NS_sig3` segue o formato confirmado
em PESQUISA.md (secao 2):

  "<METODO>&<PATH>&" + "&".join(sorted("chave=valor", incluindo o `sig`
  ja calculado)) + "&" + <nonce numerico aleatorio, sem "chave=">

Duas rotas sao usadas, ambas assinadas com o MESMO pipeline (so o PATH e
os parametros especificos da requisicao mudam):

  - `/rest/o/comment/list/v2`: comentarios principais ("rootComments").
    A resposta tem um campo `subCommentsMap`, que na pratica veio sempre
    vazio nos nossos testes (mesmo quando o `sub_comment_count` de um
    comentario e > 0) -- nao descobrimos o que faz o Kwai populá-lo
    (pode depender da versao/app especifico; ver PESQUISA.md).
  - `/rest/o/comment/sublist`: sub-comentarios (respostas) de UM
    comentario principal especifico, dado seu `rootCommentId`. Achamos o
    path/parametros documentados estaticamente (`rota-comment-list-v2.md`,
    a partir do smali) e confirmamos que funciona de verdade reusando o
    mesmo `sig`/`__NS_sig3` do v2.
"""
import random
import re
import time
from typing import List, Optional

from curl_cffi import requests as curl_requests

from . import config, kwai_sign, sig3
from .errors import InvalidUrlError, NetworkError
from .schemas import build_comentario, ms_timestamp_to_iso

METHOD = "POST"
PATH_LIST = "/rest/o/comment/list/v2"
PATH_SUBLIST = "/rest/o/comment/sublist"
URL_LIST = f"{config.KWAI_MOBILE_BASE_URL}{PATH_LIST}"
URL_SUBLIST = f"{config.KWAI_MOBILE_BASE_URL}{PATH_SUBLIST}"

_HEADERS = {
    "User-Agent": config.MOBILE_USER_AGENT,
    "Content-Type": "application/x-www-form-urlencoded",
    "Accept": "application/json",
}

_PHOTO_ID_RE = re.compile(r"/video/(\d+)")


def _extrair_photo_id(url: str) -> str:
    match = _PHOTO_ID_RE.search(url)
    if not match:
        raise InvalidUrlError(
            f"nao foi possivel extrair o photo_id da URL '{url}' "
            "(esperado algo como .../video/1234567890)"
        )
    return match.group(1)


def _montar_params(photo_id: str, pcursor: str, count: int) -> dict:
    d = config.DEVICE
    return {
        "abi": d["abi"],
        "adExtInfo": d["ad_ext_info"],
        "app": d["app"],
        "appver": d["appver"],
        "bucket": d["bucket"],
        "c": d["c"],
        "client_key": d["client_key"],
        "count": str(count),
        "countryInfo": d["countryInfo"],
        "country_code": d["country_code"],
        "did": d["did"],
        "ds": "-1",
        "egid": d["egid"],
        "isPreload": "false",
        "kpf": d["kpf"],
        "kpn": d["kpn"],
        "kwai_tiny_type": "2",
        "language": d["language"],
        "lat": "0",
        "llsid": "4888814799695302308",
        "lon": "0",
        "mcc": d["mcc"],
        "mod": d["mod"],
        "net": d["net"],
        "netScore": "19",
        "oc": "UNKNOWN",
        "order": "desc",
        "os": "android",
        "photoId": photo_id,
        "photoPageType": "0",
        "pkg": d["pkg"],
        "preloadSource": "",
        "requestType": "3",
        "session_id": d["session_id"],
        "sys": d["sys"],
        "time_zone": d["time_zone"],
        "ud": "0",
        "user_id": d["user_id"],
        "ver": d["ver"],
        "vid": d["vid"],
        "pcursor": str(pcursor),
    }


def _montar_params_sublist(photo_id: str, root_comment_id: str, pcursor: str, count: int) -> dict:
    """Mesmos campos de dispositivo do v2, mas sem os campos especificos
    de PAGINA (photoPageType/requestType/llsid/isPreload/preloadSource,
    que o smali so lista para o v2) -- e com `rootCommentId` no lugar."""
    d = config.DEVICE
    return {
        "abi": d["abi"],
        "adExtInfo": d["ad_ext_info"],
        "app": d["app"],
        "appver": d["appver"],
        "bucket": d["bucket"],
        "c": d["c"],
        "client_key": d["client_key"],
        "count": str(count),
        "countryInfo": d["countryInfo"],
        "country_code": d["country_code"],
        "did": d["did"],
        "ds": "-1",
        "egid": d["egid"],
        "kpf": d["kpf"],
        "kpn": d["kpn"],
        "language": d["language"],
        "lat": "0",
        "lon": "0",
        "mcc": d["mcc"],
        "mod": d["mod"],
        "net": d["net"],
        "oc": "UNKNOWN",
        "order": "desc",
        "os": "android",
        "photoId": photo_id,
        "pkg": d["pkg"],
        "rootCommentId": root_comment_id,
        "session_id": d["session_id"],
        "sys": d["sys"],
        "time_zone": d["time_zone"],
        "ud": "0",
        "user_id": d["user_id"],
        "ver": d["ver"],
        "vid": d["vid"],
        "pcursor": str(pcursor),
    }


def _assinar_requisicao(path: str, params: dict) -> dict:
    """Calcula `sig` e `__NS_sig3` e devolve os params prontos para enviar."""
    params = dict(params)
    params["timestamp"] = str(int(time.time() * 1000))

    sig = kwai_sign.compute_sig(params, warm=True)
    params["sig"] = sig

    nonce = str(random.randint(10 ** 17, 10 ** 18 - 1))
    sorted_pairs = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    string_to_sign = f"{METHOD}&{path}&{sorted_pairs}&{nonce}"

    params["__NS_sig3"] = sig3.assinar(string_to_sign)
    return params


def _item_para_comentario(item: dict, postagem_url: str, respondendo_a: Optional[str] = None) -> dict:
    autor_id = item.get("author_id")
    if autor_id is None:
        autor_id = item.get("user_id")
    return build_comentario(
        id_=str(item.get("comment_id")) if item.get("comment_id") is not None else None,
        postagem_url=postagem_url,
        autor_usuario=item.get("author_name"),
        autor_id=str(autor_id) if autor_id is not None else None,
        texto=item.get("content") or "",
        curtidas=item.get("liked_count"),
        data=ms_timestamp_to_iso(item.get("timestamp")),
        respondendo_a=respondendo_a,
    )


def sub_comentarios_de_comentario(photo_id: str, root_comment_id: str, postagem_url: str, limit: int = 50) -> List[dict]:
    """Busca as respostas (sub-comentarios) de UM comentario principal.
    `/rest/o/comment/sublist`, mesmo pipeline de assinatura do v2."""
    results: List[dict] = []
    pcursor = "0"
    page_size = min(config.COMMENTS_PAGE_SIZE, max(limit, 1))

    while len(results) < limit:
        params = _montar_params_sublist(photo_id, root_comment_id, pcursor, page_size)
        params = _assinar_requisicao(PATH_SUBLIST, params)

        try:
            resp = curl_requests.post(
                URL_SUBLIST, data=params, headers=_HEADERS,
                timeout=config.HTTP_TIMEOUT_SECONDS, impersonate="chrome131",
            )
        except Exception as e:
            raise NetworkError(f"falha de rede ao buscar sub-comentarios de '{root_comment_id}': {e}") from e

        if resp.status_code != 200:
            raise NetworkError(f"HTTP {resp.status_code} ao buscar sub-comentarios de '{root_comment_id}'")

        try:
            data = resp.json()
        except Exception as e:
            raise NetworkError(f"resposta invalida (nao-JSON): {e}") from e

        if data.get("result") != 1:
            break

        sub_comments = data.get("subComments") or []
        if not sub_comments:
            break

        for item in sub_comments:
            results.append(_item_para_comentario(item, postagem_url, respondendo_a=root_comment_id))
            if len(results) >= limit:
                break

        next_pcursor = data.get("pcursor")
        if not next_pcursor or next_pcursor == "no_more" or next_pcursor == pcursor:
            break
        pcursor = str(next_pcursor)

    return results[:limit]


def comentarios_de_postagem(
    postagem_url: str, limit: int = 50, incluir_subcomentarios: bool = False, subcomentarios_limit: int = 50
) -> List[dict]:
    """Busca os comentarios principais de uma postagem (`/rest/o/comment/list/v2`).

    `limit` conta so os comentarios PRINCIPAIS (nao sub-comentarios) --
    e o mesmo comportamento documentado desde antes desta funcionalidade
    existir. Se `incluir_subcomentarios=True`, para cada comentario
    principal com respostas (`sub_comment_count > 0`) buscamos as
    respostas via `/rest/o/comment/sublist` (uma chamada extra por
    comentario com resposta -- pode deixar a coleta bem mais lenta em
    postagens com muita gente respondendo)."""
    photo_id = _extrair_photo_id(postagem_url)

    results: List[dict] = []
    root_count = 0  # `limit` conta so comentarios principais -- ver docstring
    pcursor = "0"
    page_size = min(config.COMMENTS_PAGE_SIZE, max(limit, 1))

    while root_count < limit:
        params = _montar_params(photo_id, pcursor, page_size)
        params = _assinar_requisicao(PATH_LIST, params)

        try:
            resp = curl_requests.post(
                URL_LIST, data=params, headers=_HEADERS,
                timeout=config.HTTP_TIMEOUT_SECONDS, impersonate="chrome131",
            )
        except Exception as e:
            raise NetworkError(f"falha de rede ao buscar comentarios de '{postagem_url}': {e}") from e

        if resp.status_code != 200:
            raise NetworkError(f"HTTP {resp.status_code} ao buscar comentarios de '{postagem_url}'")

        try:
            data = resp.json()
        except Exception as e:
            raise NetworkError(f"resposta invalida (nao-JSON): {e}") from e

        if data.get("result") != 1:
            # Pode ser video sem comentarios, ou um erro de permissao/sessao
            # (ex.: resultado 109 == sessao de visitante rejeitada).
            break

        root_comments = data.get("rootComments") or []
        if not root_comments:
            break

        for item in root_comments:
            root_id = str(item.get("comment_id")) if item.get("comment_id") is not None else None
            results.append(_item_para_comentario(item, postagem_url))
            root_count += 1

            if incluir_subcomentarios and root_id and item.get("sub_comment_count"):
                try:
                    subs = sub_comentarios_de_comentario(photo_id, root_id, postagem_url, limit=subcomentarios_limit)
                    results.extend(subs)
                except NetworkError:
                    pass  # melhor esforco: uma thread falhar nao derruba o resto

            if root_count >= limit:
                break

        # `pcursor` e um token opaco (ex.: "r_211066486981132399",
        # "t_209818356593722276_1782291140335"), NAO um inteiro
        # incremental -- so repassamos o valor que o servidor devolveu.
        next_pcursor = data.get("pcursor")
        if not next_pcursor or next_pcursor == "no_more" or next_pcursor == pcursor:
            break
        pcursor = str(next_pcursor)

    return results

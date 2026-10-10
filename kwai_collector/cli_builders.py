"""A1_Radar."""

from __future__ import annotations

import os
from time import time
from typing import Any, Final

KWAI_BASE_URL: Final = "https://www.kwai.com"

TINY_STATIC_QUERY_PARAMS: Final[dict[str, str]] = {
    "ver": "13.7",
    "appver": "13.7.50.646302",
    "pkg": "com.kwai.video",
    "c": "GOOGLE_PLAY",
    "app": "1",
    "os": "android",
    "client_key": "3c2cd3f3",
    "kpn": "KWAI",
    "kpf": "ANDROID_PHONE",
    "kwai_tiny_type": "2",
    "sys": "KWAI_ANDROID_14",
    "mod": "samsung(SM-A356E)",
    "net": "WIFI",
    "language": "pt-br",
    "country_code": "br",
    "mcc": "724",
    "time_zone": "Brasilia Standard Time America/Sao_Paulo",
    "ds": "-1",
    "abi": "arm64-v8a",
}

MOBILE_BASE_FIELDS: Final[dict[str, str]] = {
    "os": "android",
    "client_key": "3c2cd3f3",
}

MOBILE_ENV_FIELDS: Final[dict[str, str]] = {
    "session_id": "KWAI_SESSION_ID",
    "ud": "KWAI_UD",
    "oc": "KWAI_OC",
    "llsid": "KWAI_LLSID",
    "client_salt": "KWAI_CLIENT_SALT",
}


def _env_opcional(nome: str) -> str | None:
    valor = os.getenv(nome, "").strip()
    return valor or None


def _validar_egid(egid: str) -> str:
    if not egid.startswith("DFP") or len(egid) != 64:
        raise RuntimeError("KWAI_EGID possui formato inesperado.")

    return egid


def carregar_identificadores_tiny() -> tuple[str, str]:
    did = _env_opcional("KWAI_DID")
    egid = _env_opcional("KWAI_EGID")

    if did is None:
        raise RuntimeError("KWAI_DID não foi configurado.")

    if egid is None:
        raise RuntimeError("KWAI_EGID não foi configurado.")

    return did, _validar_egid(egid)


def montar_tiny_query_params() -> dict[str, str]:
    params = dict(TINY_STATIC_QUERY_PARAMS)
    params["timestamp"] = str(int(time() * 1000))

    did = _env_opcional("KWAI_DID")
    egid = _env_opcional("KWAI_EGID")

    if did is not None:
        params["did"] = did

    if egid is not None:
        params["egid"] = _validar_egid(egid)

    return params


def montar_mobile_session_params() -> dict[str, str]:
    params = dict(MOBILE_BASE_FIELDS)

    for campo, env_name in MOBILE_ENV_FIELDS.items():
        valor = _env_opcional(env_name)

        if valor is not None:
            params[campo] = valor

    return params


def montar_url_post(post: dict[str, Any]) -> str | None:
    photo_id = post.get("photo_id_str")
    kwai_id = post.get("kwai_id")

    if not photo_id or not kwai_id:
        return None

    return f"{KWAI_BASE_URL}/@{kwai_id}/video/{photo_id}"


def primeiro_url(valor: object) -> str | None:
    if not isinstance(valor, list):
        return None

    for item in valor:
        if not isinstance(item, dict):
            continue

        url = item.get("url")

        if isinstance(url, str):
            return url

    return None


def montar_perfil(
    usuario_solicitado: str,
    posts: list[dict[str, Any]],
) -> dict[str, object]:
    primeiro_post = posts[0]

    kwai_id = primeiro_post.get("kwai_id")

    if not isinstance(kwai_id, str):
        kwai_id = usuario_solicitado

    return {
        "usuario": kwai_id,
        "nome": primeiro_post.get("user_name"),
        "id": primeiro_post.get("user_id_str"),
        "bio": primeiro_post.get("user_text"),
        "verificado": primeiro_post.get("verified"),
        "avatar": primeiro_url(primeiro_post.get("headurls")),
        "url": f"{KWAI_BASE_URL}/@{kwai_id}",
    }


def montar_post_fallback(
    post: dict[str, Any],
) -> dict[str, object]:
    photo_id = post.get("photo_id_str")
    kwai_id = post.get("kwai_id")

    url_perfil = f"{KWAI_BASE_URL}/@{kwai_id}" if isinstance(kwai_id, str) else None

    thumbnail = primeiro_url(post.get("cover_thumbnail_urls"))

    if thumbnail is None:
        thumbnail = primeiro_url(post.get("cover_first_frame_urls"))

    return {
        "photo_id": (str(photo_id) if photo_id is not None else None),
        "url": montar_url_post(post),
        "autor": {
            "nome": post.get("user_name"),
            "usuario": kwai_id,
            "id": post.get("user_id_str"),
            "url_perfil": url_perfil,
        },
        "caption": post.get("caption"),
        "descricao": None,
        "publicado_em": None,
        "data_original": post.get("time"),
        "timestamp": post.get("timestamp"),
        "duracao": None,
        "thumbnail": thumbnail,
        "engajamento": {
            "curtidas": post.get("like_count"),
            "comentarios": post.get("comment_count"),
            "compartilhamentos": post.get("forward_count"),
            "visualizacoes": post.get("view_count"),
            "curtidas_seo": None,
            "comentarios_seo": None,
        },
    }

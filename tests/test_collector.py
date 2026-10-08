"""Testes dos casos de uso com HTTP mockado (respx), sem acesso à rede."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx

from src.config import Settings
from src.container import build_services
from src.domain.exceptions import InvalidInputError, KwaiApiError
from src.infrastructure.exceptions import KwaiTransportError
from src.infrastructure.mobile_client import (
    COMMENT_HOST,
    COMMENT_PATH,
    PROFILE_FEED_PATH,
    USER_INFO_PATH,
)
from src.infrastructure.web_client import SEARCH_PATH

BASE = "https://www.kwai.com"
MOBILE_URL = COMMENT_HOST + COMMENT_PATH


@respx.mock
def test_search_parseia_e_deduplica(settings: Settings, search_response: dict[str, Any]) -> None:
    respx.post(BASE + SEARCH_PATH).mock(return_value=httpx.Response(200, json=search_response))
    with build_services(settings) as services:
        # duas palavras-chave retornam o mesmo lote -> dedup deve unir
        posts = services.search_posts.execute(["sports", "esporte"], limit=10)
    assert len(posts) == len(search_response["feeds"])
    assert all(p.coletado_em.endswith("Z") for p in posts)
    assert len({p.coletado_em for p in posts}) == 1  # um carimbo por execute


@respx.mock
def test_search_propaga_erro_de_negocio(settings: Settings) -> None:
    respx.post(BASE + SEARCH_PATH).mock(
        return_value=httpx.Response(200, json={"result": 11, "error_msg": "param"})
    )
    with build_services(settings) as services, pytest.raises(KwaiApiError) as exc:
        services.search_posts.execute(["sports"], limit=10)
    assert exc.value.result == 11


@respx.mock
def test_search_lote_sobrevive_a_feed_orfao(
    settings: Settings, search_response: dict[str, Any]
) -> None:
    """Feed órfão (sem photo_id e sem kwai_id) é ignorado sem contaminar os válidos."""
    orfao = {"caption": "sem ids", "like_count": 5}
    body = dict(search_response)
    body["feeds"] = [search_response["feeds"][0], orfao, search_response["feeds"][1]]
    respx.post(BASE + SEARCH_PATH).mock(return_value=httpx.Response(200, json=body))
    with build_services(settings) as services:
        posts = services.search_posts.execute(["sports"], limit=10)

    assert len(posts) == 2
    assert all("/video/" in p.url for p in posts)
    # um feed sem ids nunca pode virar a URL raiz
    assert all(p.url != "https://www.kwai.com/" for p in posts)


@respx.mock
def test_search_repete_em_status_transitorio_e_conclui(
    retry_settings: Settings, no_backoff: list[float], search_response: dict[str, Any]
) -> None:
    rota = respx.post(BASE + SEARCH_PATH).mock(
        side_effect=[httpx.Response(503), httpx.Response(200, json=search_response)]
    )
    with build_services(retry_settings) as services:
        posts = services.search_posts.execute(["sports"], limit=10)

    assert len(rota.calls) == 2
    assert len(posts) == len(search_response["feeds"])
    assert len(no_backoff) == 1


@respx.mock
def test_search_desiste_ao_esgotar_os_retries(
    retry_settings: Settings, no_backoff: list[float]
) -> None:
    rota = respx.post(BASE + SEARCH_PATH).mock(return_value=httpx.Response(503))
    with build_services(retry_settings) as services, pytest.raises(KwaiTransportError):
        services.search_posts.execute(["sports"], limit=10)

    assert len(rota.calls) == 3  # 1 tentativa + 2 retries
    assert len(no_backoff) == 2


@respx.mock
def test_search_nao_repete_erro_de_cliente(
    retry_settings: Settings, no_backoff: list[float]
) -> None:
    rota = respx.post(BASE + SEARCH_PATH).mock(return_value=httpx.Response(404))
    with build_services(retry_settings) as services, pytest.raises(KwaiTransportError):
        services.search_posts.execute(["sports"], limit=10)

    assert len(rota.calls) == 1
    assert no_backoff == []


def test_search_sem_palavra_chave(settings: Settings) -> None:
    with build_services(settings) as services, pytest.raises(InvalidInputError):
        services.search_posts.execute([], limit=10)


def _profile_feed_page(ids: list[str], pcursor: str) -> dict[str, Any]:
    return {
        "result": 1,
        "pcursor": pcursor,
        "feeds": [
            {
                "photo_id_str": pid,
                "kwai_id": "perfil_teste",
                "user_id_str": "u_1",
                "caption": f"post {pid}",
                "like_count": 10,
                "comment_count": 1,
                "forward_count": 2,
                "view_count": 100,
                "timestamp": 1_700_000_000_000,
            }
            for pid in ids
        ],
    }


@respx.mock
def test_user_posts_resolve_handle_pagina_e_deduplica(settings: Settings) -> None:
    """O perfil vem da API móvel: resolve o handle e pagina pelo ``pcursor``."""
    respx.post(COMMENT_HOST + USER_INFO_PATH).mock(
        return_value=httpx.Response(
            200,
            json={"result": 1, "users": [{"user_id": 150001214685137, "user_name": "Perfil"}]},
        )
    )
    respx.post(COMMENT_HOST + PROFILE_FEED_PATH).mock(
        side_effect=[
            httpx.Response(200, json=_profile_feed_page(["1", "2"], "PAGE2")),
            httpx.Response(200, json=_profile_feed_page(["2", "3"], "no_more")),
        ]
    )
    with build_services(settings) as services:
        posts = services.user_posts.execute("@perfil_teste")

    assert [p.id for p in posts] == ["1", "2", "3"]
    assert posts[0].autor.usuario == "@perfil_teste"
    assert posts[0].engajamento.compartilhamentos == 2


def test_user_posts_usuario_invalido(settings: Settings) -> None:
    with build_services(settings) as services, pytest.raises(InvalidInputError):
        services.user_posts.execute("perfil/com/barra")


def _mobile_page(ids: list[str], pcursor: str) -> dict[str, Any]:
    return {
        "result": 1,
        "commentCount": len(ids),
        "pcursor": pcursor,
        "rootComments": [
            {
                "comment_id": cid,
                "content": f"texto {cid}",
                "author_name": "usuario",
                "author_id": "1",
                "liked_count": 3,
                "timestamp": 1_700_000_000_000,
            }
            for cid in ids
        ],
    }


@respx.mock
def test_comments_pagina_e_deduplica(settings: Settings) -> None:
    respx.post(MOBILE_URL).mock(
        side_effect=[
            httpx.Response(200, json=_mobile_page(["c_1001", "c_1002"], "PAGE2")),
            httpx.Response(200, json=_mobile_page(["c_1002", "c_1003"], "no_more")),
        ]
    )
    url = "https://www.kwai.com/@perfil/video/5240651225143682227"
    with build_services(settings) as services:
        comments = services.comments.execute(url)
    # 3 comentários únicos apesar das 2 páginas com ids repetidos
    assert {c.id for c in comments} == {"c_1001", "c_1002", "c_1003"}


@respx.mock
def test_comments_anonimo_vazio(settings: Settings) -> None:
    respx.post(MOBILE_URL).mock(return_value=httpx.Response(200, json=_mobile_page([], "no_more")))
    url = "https://www.kwai.com/@perfil/video/123"
    with build_services(settings) as services:
        comments = services.comments.execute(url)
    assert comments == []


def test_comments_url_invalida(settings: Settings) -> None:
    with build_services(settings) as services, pytest.raises(InvalidInputError):
        services.comments.execute("https://www.kwai.com/@perfil")

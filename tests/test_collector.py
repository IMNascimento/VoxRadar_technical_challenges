"""Testes dos casos de uso com HTTP mockado (respx), sem acesso à rede."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx

from src.config import Settings
from src.container import build_services
from src.domain.exceptions import InvalidInputError, KwaiApiError
from src.infrastructure.mobile_client import COMMENT_HOST, COMMENT_PATH
from src.infrastructure.nuxt import FeedsData
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
def test_search_lote_sobrevive_a_feed_orfao(settings: Settings, search_response: dict[str, Any]) -> None:
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


def test_search_sem_palavra_chave(settings: Settings) -> None:
    with build_services(settings) as services, pytest.raises(InvalidInputError):
        services.search_posts.execute([], limit=10)


@respx.mock
def test_user_posts_via_ssr(
    settings: Settings,
    profile_html: str,
    profile_feeds: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    respx.get(BASE + "/@perfil_teste").mock(return_value=httpx.Response(200, text=profile_html))
    # isola a avaliação SSR devolvendo feeds conhecidos
    monkeypatch.setattr(
        "src.infrastructure.web_client.evaluate_feeds_data",
        lambda _html: FeedsData(
            feeds=profile_feeds["feeds"], cursor=profile_feeds.get("cursor")
        ),
    )
    with build_services(settings) as services:
        posts = services.user_posts.execute("@perfil_teste")
    assert len(posts) == len(profile_feeds["feeds"])
    assert posts[0].autor.usuario == "@parkourcity"


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

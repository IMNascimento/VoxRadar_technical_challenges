import pytest

from kwai_collector import config, web_client
from kwai_collector.errors import InvalidUrlError, NetworkError

from tests.helpers import FakeHttp, FakeResponse, feed_item


@pytest.fixture
def post(monkeypatch):
    """Instala um FakeHttp no lugar de curl_requests.post e o devolve."""

    def install(*responses):
        fake = FakeHttp(*responses)
        monkeypatch.setattr(web_client.curl_requests, "post", fake)
        return fake

    return install


def ok(feeds, **extra):
    return FakeResponse({"result": 1, "feeds": feeds, **extra})


# --- normalizar_handle -------------------------------------------------

@pytest.mark.parametrize(
    "entrada,esperado",
    [
        ("@perfil", "perfil"),
        ("perfil", "perfil"),
        ("  @perfil  ", "perfil"),
        ("a.b_c-d", "a.b_c-d"),
        ("https://www.kwai.com/@perfil", "perfil"),
        ("https://www.kwai.com/@perfil/video/123", "perfil"),
        ("HTTPS://WWW.KWAI.COM/@Perfil", "Perfil"),
    ],
)
def test_normalizar_handle_validos(entrada, esperado):
    assert web_client.normalizar_handle(entrada) == esperado


@pytest.mark.parametrize("entrada", ["", "   ", "com espaco", "@@x", "a/b", "ção"])
def test_normalizar_handle_invalidos(entrada):
    with pytest.raises(InvalidUrlError):
        web_client.normalizar_handle(entrada)


# --- helpers de parsing --------------------------------------------------

def test_primeira_url():
    assert web_client._primeira_url([{"url": "a"}, {"url": "b"}]) == "a"
    assert web_client._primeira_url([]) is None
    assert web_client._primeira_url(None) is None
    assert web_client._primeira_url(["nao-dict"]) is None
    assert web_client._primeira_url([{}]) is None


def test_texto_legivel_trata_placeholder_como_none():
    assert web_client._texto_legivel("...") is None
    assert web_client._texto_legivel(None) is None
    assert web_client._texto_legivel("") == ""
    assert web_client._texto_legivel("oi") == "oi"


def test_feed_item_para_postagem_completo():
    p = web_client._feed_item_to_postagem(feed_item("555", "fulano"))
    assert p["id"] == "555"
    assert p["url"] == "https://www.kwai.com/@fulano/video/555"
    assert p["autor"] == {
        "usuario": "@fulano", "id": "42", "url_perfil": "https://www.kwai.com/@fulano",
    }
    assert p["texto"] == "legenda 555"
    assert p["data_publicacao"] == "2023-11-14T22:13:20Z"
    assert p["engajamento"] == {"curtidas": 10, "comentarios": 2, "compartilhamentos": 1, "visualizacoes": 100}
    assert p["midia"] == {"video_url": "https://cdn/555.mp4", "thumbnail_url": "https://cdn/555.webp"}


def test_feed_item_usa_photo_id_numerico_se_nao_houver_str():
    item = feed_item()
    del item["photo_id_str"]
    item["photo_id"] = 777
    p = web_client._feed_item_to_postagem(item)
    assert p["id"] == "777"
    assert p["url"].endswith("/video/777")


def test_feed_item_sem_kwai_id_nem_photo_id_nao_inventa_nada():
    p = web_client._feed_item_to_postagem({"caption": "x"})
    assert p["id"] is None
    assert p["url"] == config.KWAI_WEB_BASE_URL
    assert p["autor"] == {"usuario": None, "id": None, "url_perfil": None}
    assert p["engajamento"]["curtidas"] is None
    assert p["data_publicacao"] is None
    assert p["midia"] == {"video_url": None, "thumbnail_url": None}


def test_feed_item_preserva_zero_nas_metricas():
    p = web_client._feed_item_to_postagem(feed_item(like_count=0, view_count=0))
    assert p["engajamento"]["curtidas"] == 0
    assert p["engajamento"]["visualizacoes"] == 0


def test_feed_item_caption_placeholder_vira_none():
    assert web_client._feed_item_to_postagem(feed_item(caption="..."))["texto"] is None


def test_userprofile_to_perfil():
    up = {
        "profile": {"user_id": 5, "user_name": "Nome", "userText": "bio", "verified": True, "headurl": "http://a"},
        "ownerCount": {"fan": 10, "follow": 3, "photo": 7},
    }
    p = web_client._userprofile_to_perfil("fulano", up)
    assert p["usuario"] == "@fulano"
    assert p["id"] == "5"
    assert (p["nome"], p["bio"], p["verificado"], p["avatar_url"]) == ("Nome", "bio", True, "http://a")
    assert (p["seguidores"], p["seguindo"], p["total_postagens"]) == (10, 3, 7)
    assert p["url_perfil"] == "https://www.kwai.com/@fulano"


def test_userprofile_to_perfil_vazio_e_user_text_alternativo():
    p = web_client._userprofile_to_perfil("x", {})
    assert p["id"] is None and p["seguidores"] is None and p["bio"] is None
    p = web_client._userprofile_to_perfil("x", {"profile": {"user_text": "alt"}})
    assert p["bio"] == "alt"


# --- buscar_por_palavra_chave ---------------------------------------------

@pytest.mark.parametrize("kw", ["", "   ", None])
def test_busca_palavra_chave_vazia(kw, post):
    fake = post()
    with pytest.raises(InvalidUrlError):
        web_client.buscar_por_palavra_chave(kw)
    assert fake.calls == []


def test_busca_uma_pagina_e_corpo_da_requisicao(post):
    fake = post(ok([feed_item("1"), feed_item("2")]))
    res = web_client.buscar_por_palavra_chave("futebol", limit=2)
    assert [p["id"] for p in res] == ["1", "2"]

    url, kw = fake.calls[0]
    assert url == web_client.SEARCH_URL
    assert kw["json"]["searchWord"] == "futebol"
    assert kw["json"]["pcursor"] == 0
    assert kw["json"]["count"] == config.SEARCH_PAGE_SIZE
    assert kw["impersonate"] == "chrome131"
    assert kw["timeout"] == config.HTTP_TIMEOUT_SECONDS


def test_busca_pagina_incrementando_pcursor_em_passos_de_count(post, monkeypatch):
    monkeypatch.setattr(config, "SEARCH_PAGE_SIZE", 2)
    fake = post(
        ok([feed_item("1"), feed_item("2")]),
        ok([feed_item("3"), feed_item("4")]),
        ok([feed_item("5")]),
    )
    res = web_client.buscar_por_palavra_chave("x", limit=10)
    assert [p["id"] for p in res] == ["1", "2", "3", "4", "5"]
    assert [c[1]["json"]["pcursor"] for c in fake.calls] == [0, 2, 4]


def test_busca_respeita_limit_e_nao_pede_paginas_extras(post, monkeypatch):
    monkeypatch.setattr(config, "SEARCH_PAGE_SIZE", 2)
    fake = post(ok([feed_item("1"), feed_item("2")]), ok([feed_item("3"), feed_item("4")]))
    res = web_client.buscar_por_palavra_chave("x", limit=3)
    assert [p["id"] for p in res] == ["1", "2", "3"]
    assert len(fake.calls) == 2


def test_busca_deduplica_ids_repetidos(post, monkeypatch):
    monkeypatch.setattr(config, "SEARCH_PAGE_SIZE", 2)
    post(ok([feed_item("1"), feed_item("1")]), ok([feed_item("2")]))
    res = web_client.buscar_por_palavra_chave("x", limit=10)
    assert [p["id"] for p in res] == ["1", "2"]


def test_busca_para_se_pagina_so_traz_repetidos(post, monkeypatch):
    monkeypatch.setattr(config, "SEARCH_PAGE_SIZE", 2)
    fake = post(ok([feed_item("1"), feed_item("2")]), ok([feed_item("1"), feed_item("2")]))
    res = web_client.buscar_por_palavra_chave("x", limit=10)
    assert len(res) == 2
    assert len(fake.calls) == 2


def test_busca_result_diferente_de_1_encerra_sem_erro(post):
    post(FakeResponse({"result": 109}))
    assert web_client.buscar_por_palavra_chave("x") == []


@pytest.mark.parametrize("payload", [{"result": 1}, {"result": 1, "feeds": []}, {"result": 1, "feeds": None}])
def test_busca_sem_feeds_devolve_vazio(post, payload):
    post(FakeResponse(payload))
    assert web_client.buscar_por_palavra_chave("x") == []


def test_busca_http_nao_200_levanta_network_error(post):
    post(FakeResponse(status_code=503))
    with pytest.raises(NetworkError, match="503"):
        web_client.buscar_por_palavra_chave("x")


def test_busca_resposta_nao_json_levanta_network_error(post):
    post(FakeResponse(json_error=ValueError("boom")))
    with pytest.raises(NetworkError, match="nao-JSON"):
        web_client.buscar_por_palavra_chave("x")


def test_busca_excecao_de_rede_levanta_network_error(post):
    post(ConnectionError("dns"))
    with pytest.raises(NetworkError, match="falha de rede"):
        web_client.buscar_por_palavra_chave("x")


# --- carregar_perfil / postagens do perfil -----------------------------------

PERFIL_OK = {
    "userProfile": {
        "profile": {"user_id": 1, "user_name": "Fulano"},
        "ownerCount": {"fan": 1, "follow": 2, "photo": 3},
    }
}


def test_carregar_perfil_com_postagens(post):
    fake = post(
        FakeResponse(PERFIL_OK),
        FakeResponse({"result": 1, "feeds": [feed_item("1"), feed_item("2")], "cursor": "no_more"}),
    )
    perfil, postagens = web_client.carregar_perfil("@fulano", limit=10)

    assert perfil["nome"] == "Fulano"
    assert [p["id"] for p in postagens] == ["1", "2"]

    (url_perfil, kw_perfil), (url_feed, kw_feed) = fake.calls
    assert url_perfil == web_client.PROFILE_URL
    assert kw_perfil["json"]["userId"] == "fulano"  # sem "@" no /profile
    assert url_feed == web_client.PROFILE_FEED_URL
    assert kw_feed["json"]["userId"] == "@fulano"  # com "@" no /feed/profile
    assert "pcursor" not in kw_feed["json"]


def test_carregar_perfil_sem_user_profile_devolve_none(post):
    post(FakeResponse({}), FakeResponse({"result": 1, "feeds": [], "cursor": "no_more"}))
    perfil, postagens = web_client.carregar_perfil("fulano")
    assert perfil is None
    assert postagens == []


def test_carregar_perfil_handle_invalido_nao_faz_requisicao(post):
    fake = post()
    with pytest.raises(InvalidUrlError):
        web_client.carregar_perfil("com espaco")
    assert fake.calls == []


def test_carregar_perfil_erro_http_no_perfil(post):
    post(FakeResponse(status_code=500))
    with pytest.raises(NetworkError, match="carregar perfil"):
        web_client.carregar_perfil("fulano")


def test_postagens_paginam_com_cursor_do_servidor(post):
    fake = post(
        FakeResponse({"result": 1, "feeds": [feed_item("1"), feed_item("2")], "cursor": "c1"}),
        FakeResponse({"result": 1, "feeds": [feed_item("3")], "cursor": "no_more"}),
    )
    res = web_client._postagens_do_perfil("fulano", limit=10)
    assert [p["id"] for p in res] == ["1", "2", "3"]
    assert "pcursor" not in fake.calls[0][1]["json"]
    assert fake.calls[1][1]["json"]["pcursor"] == "c1"


@pytest.mark.parametrize("cursor", [None, "", "no_more"])
def test_postagens_param_sem_cursor_utilizavel(post, cursor):
    fake = post(FakeResponse({"result": 1, "feeds": [feed_item("1")], "cursor": cursor}))
    res = web_client._postagens_do_perfil("fulano", limit=10)
    assert len(res) == 1
    assert len(fake.calls) == 1


def test_postagens_respeitam_limit(post):
    post(FakeResponse({"result": 1, "feeds": [feed_item("1"), feed_item("2"), feed_item("3")], "cursor": "c"}))
    res = web_client._postagens_do_perfil("fulano", limit=2)
    assert [p["id"] for p in res] == ["1", "2"]


def test_postagens_param_se_cursor_nao_trouxe_nada_novo(post):
    fake = post(
        FakeResponse({"result": 1, "feeds": [feed_item("1")], "cursor": "c1"}),
        FakeResponse({"result": 1, "feeds": [feed_item("1")], "cursor": "c2"}),
    )
    res = web_client._postagens_do_perfil("fulano", limit=10)
    assert len(res) == 1
    assert len(fake.calls) == 2


def test_postagens_result_diferente_de_1(post):
    post(FakeResponse({"result": 2}))
    assert web_client._postagens_do_perfil("fulano", limit=10) == []


def test_postagens_do_usuario_atalho_normaliza_handle(post):
    fake = post(FakeResponse({"result": 1, "feeds": [feed_item("1")], "cursor": "no_more"}))
    res = web_client.postagens_do_usuario("https://www.kwai.com/@fulano", limit=5)
    assert len(res) == 1
    assert fake.calls[0][1]["json"]["userId"] == "@fulano"

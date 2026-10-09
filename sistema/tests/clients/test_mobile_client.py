import re

import pytest

from kwai_collector import config, kwai_sign, mobile_client
from kwai_collector.errors import InvalidUrlError, NetworkError, Sig3ServiceUnavailableError

from tests.helpers import FakeHttp, FakeResponse

URL = "https://www.kwai.com/@luansantana/video/5252754643917268877"
PHOTO_ID = "5252754643917268877"


@pytest.fixture
def sig3_falso(monkeypatch):
    """Substitui o servico __NS_sig3 e registra as strings assinadas."""
    assinadas = []

    def assinar(s):
        assinadas.append(s)
        return "SIG3FAKE"

    monkeypatch.setattr(mobile_client.sig3, "assinar", assinar)
    return assinadas


@pytest.fixture
def post(monkeypatch, sig3_falso):
    def install(*responses):
        fake = FakeHttp(*responses)
        monkeypatch.setattr(mobile_client.curl_requests, "post", fake)
        return fake

    return install


def comentario(cid, texto="oi", **extra):
    c = {
        "comment_id": cid, "author_id": 7, "author_name": "Autor", "content": texto,
        "liked_count": 3, "timestamp": 1_700_000_000_000,
    }
    c.update(extra)
    return c


def lista(comments, pcursor="no_more", result=1):
    return FakeResponse({"result": result, "rootComments": comments, "pcursor": pcursor})


def sublista(subs, pcursor="no_more", result=1):
    return FakeResponse({"result": result, "subComments": subs, "pcursor": pcursor})


# --- helpers ------------------------------------------------------------

def test_extrair_photo_id():
    assert mobile_client._extrair_photo_id(URL) == PHOTO_ID
    assert mobile_client._extrair_photo_id("https://x/video/123?foo=1") == "123"


@pytest.mark.parametrize("url", ["", "https://www.kwai.com/@x", "https://www.kwai.com/@x/video/abc"])
def test_extrair_photo_id_invalido(url):
    with pytest.raises(InvalidUrlError):
        mobile_client._extrair_photo_id(url)


def test_montar_params_usa_device_e_argumentos():
    p = mobile_client._montar_params(PHOTO_ID, "r_1", 20)
    assert p["photoId"] == PHOTO_ID
    assert p["pcursor"] == "r_1"
    assert p["count"] == "20"
    assert p["did"] == config.DEVICE["did"]
    assert p["client_key"] == config.DEVICE["client_key"]
    assert all(isinstance(v, str) for v in p.values())


def test_montar_params_sublist_tem_root_comment_id_e_sem_campos_de_pagina():
    p = mobile_client._montar_params_sublist(PHOTO_ID, "99", "0", 5)
    assert p["rootCommentId"] == "99"
    assert p["photoId"] == PHOTO_ID
    for campo in ("photoPageType", "requestType", "llsid", "isPreload", "preloadSource"):
        assert campo not in p


def test_assinar_requisicao_gera_sig_e_sig3_sobre_string_canonica(sig3_falso):
    base = {"b": "2", "a": "1"}
    out = mobile_client._assinar_requisicao("/rest/x", base)

    assert "sig" not in base and "timestamp" not in base  # nao muta a entrada
    assert out["__NS_sig3"] == "SIG3FAKE"
    assert out["timestamp"].isdigit()

    sem_saidas = {k: v for k, v in out.items() if k not in ("sig", "__NS_sig3")}
    assert out["sig"] == kwai_sign.compute_sig(sem_saidas, warm=True)

    (assinada,) = sig3_falso
    m = re.fullmatch(r"POST&/rest/x&(.+)&(\d{18})", assinada)
    assert m, assinada
    pares = m.group(1).split("&")
    assert pares == sorted(pares)
    assert f"sig={out['sig']}" in pares
    assert "a=1" in pares and "b=2" in pares
    assert not any(p.startswith("__NS_sig3") for p in pares)


# --- comentarios_de_postagem -----------------------------------------------

def test_comentarios_url_invalida_nao_chama_rede(post):
    fake = post()
    with pytest.raises(InvalidUrlError):
        mobile_client.comentarios_de_postagem("https://www.kwai.com/@x")
    assert fake.calls == []


def test_comentarios_uma_pagina_mapeia_campos_e_envia_form(post):
    fake = post(lista([comentario(1, "primeiro")]))
    res = mobile_client.comentarios_de_postagem(URL, limit=10)

    assert len(res) == 1
    c = res[0]
    assert c["id"] == "1"
    assert c["postagem_url"] == URL
    assert c["autor"] == {"usuario": "Autor", "id": "7"}
    assert c["texto"] == "primeiro"
    assert c["curtidas"] == 3
    assert c["data"] == "2023-11-14T22:13:20Z"
    assert c["respondendo_a"] is None

    url, kw = fake.calls[0]
    assert url == mobile_client.URL_LIST
    assert kw["data"]["photoId"] == PHOTO_ID
    assert kw["data"]["__NS_sig3"] == "SIG3FAKE"
    assert kw["data"]["sig"]
    assert kw["impersonate"] == "chrome131"


def test_comentarios_pagina_repassando_pcursor_opaco(post):
    fake = post(
        lista([comentario(1)], pcursor="r_100"),
        lista([comentario(2)], pcursor="t_200_1"),
        lista([comentario(3)], pcursor="no_more"),
    )
    res = mobile_client.comentarios_de_postagem(URL, limit=10)
    assert [c["id"] for c in res] == ["1", "2", "3"]
    assert [call[1]["data"]["pcursor"] for call in fake.calls] == ["0", "r_100", "t_200_1"]


def test_comentarios_para_se_pcursor_se_repete(post):
    fake = post(lista([comentario(1)], pcursor="0"))
    mobile_client.comentarios_de_postagem(URL, limit=10)
    assert len(fake.calls) == 1


def test_comentarios_limit_e_respeitado_dentro_da_pagina(post):
    fake = post(lista([comentario(1), comentario(2), comentario(3)], pcursor="x"))
    res = mobile_client.comentarios_de_postagem(URL, limit=2)
    assert [c["id"] for c in res] == ["1", "2"]
    assert len(fake.calls) == 1


def test_comentarios_page_size_e_min_entre_config_e_limit(post, monkeypatch):
    monkeypatch.setattr(config, "COMMENTS_PAGE_SIZE", 20)
    fake = post(lista([]), lista([]))
    mobile_client.comentarios_de_postagem(URL, limit=5)
    mobile_client.comentarios_de_postagem(URL, limit=500)
    assert fake.calls[0][1]["data"]["count"] == "5"
    assert fake.calls[1][1]["data"]["count"] == "20"


def test_comentarios_result_diferente_de_1_devolve_vazio(post):
    post(lista([], result=109))
    assert mobile_client.comentarios_de_postagem(URL) == []


def test_comentarios_sem_root_comments_devolve_vazio(post):
    post(FakeResponse({"result": 1}))
    assert mobile_client.comentarios_de_postagem(URL) == []


def test_comentarios_cai_para_user_id_se_nao_ha_author_id(post):
    item = comentario(1)
    del item["author_id"]
    item["user_id"] = 55
    post(lista([item]))
    assert mobile_client.comentarios_de_postagem(URL)[0]["autor"]["id"] == "55"


def test_comentarios_campos_ausentes_viram_none_ou_vazio(post):
    post(lista([{}]))
    c = mobile_client.comentarios_de_postagem(URL)[0]
    assert c["id"] is None
    assert c["texto"] == ""
    assert c["curtidas"] is None
    assert c["data"] is None
    assert c["autor"] == {"usuario": None, "id": None}


def test_comentarios_http_nao_200(post):
    post(FakeResponse(status_code=403))
    with pytest.raises(NetworkError, match="403"):
        mobile_client.comentarios_de_postagem(URL)


def test_comentarios_nao_json(post):
    post(FakeResponse(json_error=ValueError("x")))
    with pytest.raises(NetworkError, match="nao-JSON"):
        mobile_client.comentarios_de_postagem(URL)


def test_comentarios_falha_de_rede(post):
    post(ConnectionError("down"))
    with pytest.raises(NetworkError, match="falha de rede"):
        mobile_client.comentarios_de_postagem(URL)


def test_comentarios_propaga_servico_sig3_indisponivel(monkeypatch):
    def assinar(_):
        raise Sig3ServiceUnavailableError("fora do ar")

    monkeypatch.setattr(mobile_client.sig3, "assinar", assinar)
    with pytest.raises(Sig3ServiceUnavailableError):
        mobile_client.comentarios_de_postagem(URL)


# --- sub-comentarios ----------------------------------------------------

def test_subcomentarios_nao_buscados_por_padrao(post):
    fake = post(lista([comentario(1, sub_comment_count=2)]))
    res = mobile_client.comentarios_de_postagem(URL)
    assert len(res) == 1
    assert len(fake.calls) == 1


def test_subcomentarios_buscados_so_para_quem_tem_respostas(post):
    fake = post(
        lista([comentario(1, sub_comment_count=1), comentario(2, sub_comment_count=0), comentario(3)]),
        sublista([comentario(10, "resposta")]),
    )
    res = mobile_client.comentarios_de_postagem(URL, incluir_subcomentarios=True)

    assert [c["id"] for c in res] == ["1", "10", "2", "3"]
    sub = res[1]
    assert sub["respondendo_a"] == "1"
    assert sub["texto"] == "resposta"

    assert len(fake.calls) == 2
    url, kw = fake.calls[1]
    assert url == mobile_client.URL_SUBLIST
    assert kw["data"]["rootCommentId"] == "1"


def test_limit_conta_so_comentarios_principais(post):
    post(
        lista([comentario(1, sub_comment_count=2), comentario(2)]),
        sublista([comentario(10), comentario(11)]),
    )
    res = mobile_client.comentarios_de_postagem(URL, limit=2, incluir_subcomentarios=True)
    assert [c["id"] for c in res] == ["1", "10", "11", "2"]


def test_erro_de_rede_em_subcomentarios_nao_derruba_a_coleta(post):
    post(
        lista([comentario(1, sub_comment_count=1), comentario(2)]),
        ConnectionError("down"),
    )
    res = mobile_client.comentarios_de_postagem(URL, incluir_subcomentarios=True)
    assert [c["id"] for c in res] == ["1", "2"]


def test_sub_comentarios_paginacao_e_limit(post):
    fake = post(
        sublista([comentario(10), comentario(11)], pcursor="p2"),
        sublista([comentario(12), comentario(13)], pcursor="no_more"),
    )
    res = mobile_client.sub_comentarios_de_comentario(PHOTO_ID, "1", URL, limit=3)
    assert [c["id"] for c in res] == ["10", "11", "12"]
    assert all(c["respondendo_a"] == "1" for c in res)
    assert [call[1]["data"]["pcursor"] for call in fake.calls] == ["0", "p2"]


def test_sub_comentarios_result_ruim_ou_vazio(post):
    post(sublista([], result=5), sublista([]))
    assert mobile_client.sub_comentarios_de_comentario(PHOTO_ID, "1", URL) == []
    assert mobile_client.sub_comentarios_de_comentario(PHOTO_ID, "1", URL) == []


def test_sub_comentarios_http_erro(post):
    post(FakeResponse(status_code=500))
    with pytest.raises(NetworkError, match="500"):
        mobile_client.sub_comentarios_de_comentario(PHOTO_ID, "1", URL)

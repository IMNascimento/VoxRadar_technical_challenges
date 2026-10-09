"""Testes dos proprios fakes (helpers.py) e das fixtures (conftest.py): se
eles mentirem, todos os outros testes perdem o valor."""
import pytest
import requests

from tests.helpers import FakeHttp, FakeResponse, feed_item


# --- FakeResponse -------------------------------------------------------

def test_fake_response_padroes():
    r = FakeResponse()
    assert r.status_code == 200
    assert r.text == ""
    assert r.json() is None
    assert list(r.iter_content()) == []
    r.raise_for_status()  # 200 nao levanta


def test_fake_response_json_e_texto():
    r = FakeResponse({"a": 1}, text="ok")
    assert r.json() == {"a": 1}
    assert r.text == "ok"


def test_fake_response_json_error_levanta_a_excecao_dada():
    r = FakeResponse(json_error=ValueError("x"))
    with pytest.raises(ValueError, match="x"):
        r.json()


@pytest.mark.parametrize("status,levanta", [(200, False), (204, False), (399, False), (400, True), (500, True)])
def test_fake_response_raise_for_status(status, levanta):
    r = FakeResponse(status_code=status)
    if levanta:
        with pytest.raises(requests.HTTPError, match=str(status)):
            r.raise_for_status()
    else:
        r.raise_for_status()


def test_fake_response_iter_content_devolve_chunks_na_ordem():
    r = FakeResponse(chunks=[b"a", b"b"])
    assert list(r.iter_content(chunk_size=1)) == [b"a", b"b"]


# --- FakeHttp -----------------------------------------------------------

def test_fake_http_devolve_respostas_em_ordem_e_registra_chamadas():
    r1, r2 = FakeResponse(text="1"), FakeResponse(text="2")
    http = FakeHttp(r1, r2)

    assert http("http://a", json={"x": 1}) is r1
    assert http("http://b") is r2
    assert http.calls == [("http://a", {"json": {"x": 1}}), ("http://b", {})]


def test_fake_http_levanta_excecao_enfileirada():
    http = FakeHttp(ConnectionError("down"), FakeResponse())
    with pytest.raises(ConnectionError, match="down"):
        http("http://a")
    assert isinstance(http("http://b"), FakeResponse)  # segue a fila depois da falha
    assert len(http.calls) == 2  # a chamada que falhou tambem foi registrada


def test_fake_http_sem_respostas_sobrando_falha_alto():
    http = FakeHttp(FakeResponse())
    http("http://a")
    with pytest.raises(AssertionError, match="inesperada: http://b"):
        http("http://b")


def test_fake_http_vazio_nao_aceita_nenhuma_chamada():
    with pytest.raises(AssertionError):
        FakeHttp()("http://a")


def test_fake_http_nao_compartilha_estado_entre_instancias():
    a, b = FakeHttp(FakeResponse()), FakeHttp(FakeResponse())
    a("http://x")
    assert b.calls == [] and len(b.responses) == 1


# --- feed_item / fixture make_feed_item ----------------------------------

def test_feed_item_valores_padrao_derivam_do_photo_id():
    item = feed_item("555", "fulano")
    assert item["photo_id_str"] == "555"
    assert item["kwai_id"] == "fulano"
    assert item["caption"] == "legenda 555"
    assert item["main_mv_urls"] == [{"url": "https://cdn/555.mp4"}]
    assert item["cover_thumbnail_urls"] == [{"url": "https://cdn/555.webp"}]


def test_feed_item_extra_sobrescreve_e_adiciona_campos():
    item = feed_item(like_count=0, novo="x")
    assert item["like_count"] == 0
    assert item["novo"] == "x"
    assert item["comment_count"] == 2  # o resto permanece


def test_feed_item_devolve_dicts_independentes():
    a, b = feed_item("1"), feed_item("1")
    a["main_mv_urls"].append({"url": "outra"})
    assert len(b["main_mv_urls"]) == 1


def test_fixture_make_feed_item_e_o_builder(make_feed_item):
    assert make_feed_item is feed_item
    assert make_feed_item("9")["photo_id_str"] == "9"

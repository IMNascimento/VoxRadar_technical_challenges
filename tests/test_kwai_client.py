import httpx
import pytest

from kwai_collector.clients import kwai_client
from kwai_collector.clients.kwai_client import search_posts


class FakeResponse:
    def raise_for_status(self):
        pass

    def json(self):
        return {
            "feeds": [
                {
                    "photo_id_str": "1234567890",
                    "kwai_id": "usuario_teste",
                },
                {
                    "photo_id_str": "0987654321",
                    "kwai_id": "usuario_teste2",
                },
            ]
        }


def test_search_posts_retorna_lista_de_feeds(monkeypatch):
    def fake_post(*args, **kwargs):
        assert kwargs["json"]["searchWord"] == "teste"
        return FakeResponse()

    monkeypatch.setattr(httpx, "post", fake_post)

    resultado = search_posts("teste")

    assert isinstance(resultado, list)
    assert len(resultado) == 2
    assert resultado[0]["photo_id_str"] == "1234567890"
    assert resultado[1]["photo_id_str"] == "0987654321"


def test_search__post_tenta_novamente_em_erro_temporario(monkeypatch):
    tentativas = 0

    def fake_post(*args, **kwargs):
        nonlocal tentativas
        tentativas += 1

        if tentativas < 3:
            raise httpx.RequestError("Erro temporário")

        return FakeResponse()

    monkeypatch.setattr(httpx, "post", fake_post)

    resultado = search_posts(
        "teste",
        backoff_base=0,
    )

    assert tentativas == 3
    assert len(resultado) == 2


def test_search_posts_lanca_erro_apos_max_tentativas(monkeypatch):
    tentativas = 0

    def fake_post(*args, **kwargs):
        nonlocal tentativas
        tentativas += 1
        raise httpx.RequestError("Kwai indisponível")

    monkeypatch.setattr(httpx, "post", fake_post)

    with pytest.raises(httpx.RequestError):
        search_posts(
            "teste",
            max_tentativas=3,
            backoff_base=0,
        )

    assert tentativas == 3


def test_search_posts_tenta_novamente_em_erro_503(monkeypatch):
    tentativas = 0

    def fake_post(*args, **kwargs):
        nonlocal tentativas
        tentativas += 1

        request = httpx.Request(
            "POST",
            "https://www.kwai.com/teste",
        )

        if tentativas < 3:
            return httpx.Response(
                status_code=503,
                request=request,
            )

        return FakeResponse()

    monkeypatch.setattr(httpx, "post", fake_post)

    resultado = search_posts(
        "teste",
        backoff_base=0,
    )

    assert tentativas == 3
    assert len(resultado) == 2


def test_search_posts_nao_repete_em_erro_404(monkeypatch):
    tentativas = 0

    def fake_post(*args, **kwargs):
        nonlocal tentativas
        tentativas += 1

        request = httpx.Request(
            "POST",
            "https://www.kwai.com/teste",
        )

        return httpx.Response(
            status_code=404,
            request=request,
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    with pytest.raises(httpx.HTTPStatusError):
        search_posts(
            "teste",
            max_tentativas=3,
            backoff_base=0,
        )

    assert tentativas == 1


def test_search_all_posts_remove_duplicados(monkeypatch):
    paginas = {
        0: [
            {"photo_id_str": "111"},
            {"photo_id_str": "222"},
        ],
        1: [
            {"photo_id_str": "222"},
            {"photo_id_str": "333"},
        ],
    }

    def fake_search_posts(keyword, pcursor=0, **kwargs):
        return paginas.get(pcursor, [])

    monkeypatch.setattr(
        kwai_client,
        "search_posts",
        fake_search_posts,
    )

    resultado = kwai_client.search_all_posts("teste", max_paginas=2)

    assert len(resultado) == 3
    assert resultado[0]["photo_id_str"] == "111"
    assert resultado[1]["photo_id_str"] == "222"
    assert resultado[2]["photo_id_str"] == "333"


def test_search_all_posts_para_quando_pagina_vazia(monkeypatch):
    cursores_chamados = []

    def fake_search_posts(keyword, pcursor=0, **kwargs):
        cursores_chamados.append(pcursor)
        if pcursor == 0:
            return [
                {"photo_id_str": "111"},
                {"photo_id_str": "222"},
            ]
        return []

    monkeypatch.setattr(
        kwai_client,
        "search_posts",
        fake_search_posts,
    )

    resultado = kwai_client.search_all_posts("teste", max_paginas=5)
    assert len(resultado) == 2
    assert cursores_chamados == [0, 1]

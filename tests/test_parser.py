import pytest
from pydantic import ValidationError

from kwai_collector.models import Post
from kwai_collector.parser import ms_to_iso, parse_comment, parse_post, parse_posts, to_int
from tests.conftest import load

NOW = "2026-01-01T00:00:00Z"


def test_parse_post_da_busca():
    feed = load("search_response.json")["feeds"][0]
    post = parse_post(feed, NOW)

    assert post is not None
    assert post.id == feed["photo_id_str"]
    assert post.url == f"https://www.kwai.com/@{feed['kwai_id']}/video/{feed['photo_id_str']}"
    assert post.autor.usuario == "@" + feed["kwai_id"]
    assert post.engajamento.curtidas == int(feed["like_count"])
    assert post.coletado_em == NOW


def test_post_sem_id_e_ignorado():
    posts = parse_posts([{"caption": "oi"}, "lixo", {"photo_id": 1, "kwai_id": "a"}], NOW)
    assert len(posts) == 1
    assert posts[0].url == "https://www.kwai.com/@a/video/1"


def test_metrica_ausente_fica_none():
    post = parse_post({"photo_id": 1, "kwai_id": "a"}, NOW)
    assert post is not None
    assert post.engajamento.visualizacoes is None
    assert post.texto is None


def test_parse_comment():
    raw = load("mobile_comments.json")[0]["rootComments"][0]
    comment = parse_comment(raw, "https://www.kwai.com/@a/video/1", NOW)

    assert comment.id == "155133451079517322"
    assert comment.autor.usuario == "Gonzaga da fz 25"
    assert comment.autor.id == "150001404765512"
    assert comment.curtidas == 427
    assert comment.data == "2024-11-11T21:49:22Z"


def test_texto_com_html_escapado():
    comment = parse_comment({"content": "a &amp; b"}, "u", NOW)
    assert comment.texto == "a & b"


def test_modelo_rejeita_data_fora_do_padrao():
    with pytest.raises(ValidationError):
        Post(url="u", autor={}, engajamento={}, coletado_em="ontem")


def test_to_int_e_ms_to_iso():
    assert to_int("10") == 10
    assert to_int(True) is None
    assert to_int("abc") is None
    assert ms_to_iso(0) is None
    assert ms_to_iso("1731361762640") == "2024-11-11T21:49:22Z"

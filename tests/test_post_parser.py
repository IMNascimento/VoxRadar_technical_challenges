from datetime import datetime

from kwai_collector.models.postagem import Postagem
from kwai_collector.parsers.post_parser import parse_post


def test_parse_post_retorna_postagem():
    post_bruto = {
        "kwai_id": "viciado_futebol",
        "photo_id_str": "5220666497460442264",
        "user_name": "Viciado no Futebol",
        "user_id_str": "123456",
        "caption": "Teste de postagem",
        "time": "2024-10-03 06:42:01",
        "like_count": 100,
        "comment_count": 20,
        "forward_count": 5,
        "view_count": 1000,
    }

    resultado = parse_post(post_bruto)
    assert isinstance(resultado, Postagem)
    assert resultado.id == "5220666497460442264"
    assert (
        resultado.url
        == "https://www.kwai.com/@viciado_futebol/video/5220666497460442264"
    )

    assert resultado.autor.usuario == "Viciado no Futebol"
    assert resultado.autor.id == "123456"
    assert resultado.autor.url_perfil == "https://www.kwai.com/@viciado_futebol"

    assert resultado.texto == "Teste de postagem"

    assert resultado.engajamento.curtidas == 100
    assert resultado.engajamento.comentarios == 20
    assert resultado.engajamento.compartilhamentos == 5
    assert resultado.engajamento.visualizacoes == 1000


def test_parse_post_com_campos_ausente():
    post_bruto = {
        "kwai_id": "usuario_teste",
        "photo_id_str": "9999999",
        "user_name": "Usuario Teste",
        "user_id_str": "987654",
    }

    resultado = parse_post(post_bruto)
    assert isinstance(resultado, Postagem)

    assert resultado.id == "9999999"
    assert resultado.url == "https://www.kwai.com/@usuario_teste/video/9999999"

    assert resultado.autor.usuario == "Usuario Teste"
    assert resultado.autor.id == "987654"
    assert resultado.autor.url_perfil == "https://www.kwai.com/@usuario_teste"

    assert resultado.texto is None
    assert resultado.data_publicacao is None

    assert resultado.engajamento.curtidas is None
    assert resultado.engajamento.comentarios is None
    assert resultado.engajamento.compartilhamentos is None
    assert resultado.engajamento.visualizacoes is None


def teste_parse_post_converte_data_publicacao():
    post_bruto = {
        "kwai_id": "usuario_teste",
        "photo_id_str": "9999999",
        "user_name": "Usuario Teste",
        "user_id_str": "987654",
        "time": "2024-10-03 06:42:01",
    }

    resultado = parse_post(post_bruto)
    assert isinstance(resultado.data_publicacao, datetime)

    assert resultado.data_publicacao.year == 2024
    assert resultado.data_publicacao.month == 10
    assert resultado.data_publicacao.day == 3
    assert resultado.data_publicacao.hour == 6
    assert resultado.data_publicacao.minute == 42
    assert resultado.data_publicacao.second == 1

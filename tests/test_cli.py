import json

import pytest

from kwai_collector import cli
from kwai_collector.cli import main
from kwai_collector.config import Settings
from kwai_collector.parsers.comment_parser import (
    parse_comment as parse_comment_real,
)
from kwai_collector.parsers.post_parser import (
    parse_post as parse_post_real,
)


@pytest.fixture(autouse=True)
def isolated_cli_settings(monkeypatch):

    # Local session settings must not select routes or enter unit-test requests.

    monkeypatch.setattr(
        cli,
        "settings",
        Settings(
            _env_file=None,
            cookie=None,
            mobile_page_delay=0,
            mobile_query_fields={},
            mobile_body_fields={},
            mobile_header_fields={},
            mobile_auth_endpoint=None,
            mobile_auth_token=None,
        ),
    )


def criar_post(
    indice: int,
) -> dict[str, object]:

    photo_id = f"52535990778134066{indice:02d}"

    return {
        "kwai_id": "perfil_teste",
        "photo_id_str": photo_id,
        "user_name": "Perfil Teste",
        "user_id_str": "123456",
        "user_text": "Bio do perfil",
        "verified": False,
        "caption": f"Post {indice}",
        "time": "2026-09-14 12:00:00",
        "timestamp": 1789400000000 + indice,
        "like_count": 100 + indice,
        "comment_count": 30,
        "forward_count": 5,
        "view_count": 1000 + indice,
        "headurls": [{"url": ("https://example.com/avatar.jpg")}],
        "cover_thumbnail_urls": [{"url": (f"https://example.com/capa-{indice}.jpg")}],
    }


def test_cli_coleta_10_posts_e_comentarios(
    monkeypatch,
    tmp_path,
):

    monkeypatch.setenv(
        "KWAI_DID",
        "did_teste",
    )

    monkeypatch.setenv(
        "KWAI_EGID",
        "DFPAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    )

    posts = [criar_post(indice) for indice in range(12)]

    def fake_get_all_profile_posts(
        user_id,
        max_paginas=1,
        delay=0.0,
    ):

        assert user_id == "@perfil_teste"

        assert max_paginas == 1

        assert delay == 0.0

        return posts

    chamadas_detalhes: list[str] = []

    def fake_get_post_details(
        url,
        expected_photo_id=None,
    ):

        assert expected_photo_id is not None

        chamadas_detalhes.append(expected_photo_id)

        return {
            "photo_id": expected_photo_id,
            "url": url,
            "autor": {
                "nome": "Perfil Teste",
                "usuario": "perfil_teste",
                "id": "123456",
                "url_perfil": ("https://www.kwai.com/@perfil_teste"),
            },
            "caption": "Post de teste",
            "descricao": "Descrição",
            "publicado_em": ("2026-09-14T12:00:00Z"),
            "data_original": ("2026-09-14 12:00:00"),
            "timestamp": 1789400000000,
            "duracao": "PT1M",
            "thumbnail": ("https://example.com/capa.jpg"),
            "engajamento": {
                "curtidas": 100,
                "comentarios": 30,
                "compartilhamentos": 5,
                "visualizacoes": 1000,
                "curtidas_seo": None,
                "comentarios_seo": None,
            },
        }

    chamadas_comentarios: list[str] = []

    def fake_get_tiny_comments(
        photo_id,
        query_params=None,
        debug=False,
    ):

        chamadas_comentarios.append(photo_id)

        return [
            {
                "commentId": indice,
                "userName": (f"Usuario {indice}"),
                "kwaiid": (f"usuario{indice}"),
                "content": (f"Comentario {indice}"),
                "commentLikeCount": indice,
            }
            for indice in range(20)
        ]

    monkeypatch.setattr(
        cli,
        "get_all_profile_posts",
        fake_get_all_profile_posts,
    )

    monkeypatch.setattr(
        cli,
        "get_post_details",
        fake_get_post_details,
    )

    monkeypatch.setattr(
        cli,
        "get_tiny_comments",
        fake_get_tiny_comments,
    )

    codigo = main(
        [
            "@perfil_teste",
            "--output-dir",
            str(tmp_path),
            "--delay",
            "0",
        ]
    )

    assert codigo == 0

    arquivo_posts = tmp_path / "perfil_teste_posts.json"

    arquivo_comentarios = tmp_path / "perfil_teste_comentarios.json"

    assert arquivo_posts.exists()

    assert arquivo_comentarios.exists()

    dados_posts = json.loads(arquivo_posts.read_text(encoding="utf-8"))

    dados_comentarios = json.loads(arquivo_comentarios.read_text(encoding="utf-8"))

    assert dados_posts["total_posts_coletados"] == 10

    assert len(dados_posts["posts"]) == 10

    assert dados_comentarios["total_posts_processados"] == 10

    assert dados_comentarios["total_comentarios_coletados"] == 200

    assert len(chamadas_detalhes) == 10

    assert len(chamadas_comentarios) == 10

    for post in dados_comentarios["posts"]:
        assert post["quantidade"] == 20

        assert len(post["comentarios"]) == 20


def test_cli_sem_posts_retorna_erro(
    monkeypatch,
    tmp_path,
):

    def fake_get_all_profile_posts(
        user_id,
        max_paginas=1,
        delay=0.0,
    ):

        return []

    monkeypatch.setattr(
        cli,
        "get_all_profile_posts",
        fake_get_all_profile_posts,
    )

    codigo = main(
        [
            "@perfil_vazio",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert codigo == 1


def test_cli_buscar_posts_por_palavra_chave(
    monkeypatch,
    tmp_path,
):

    posts = [
        criar_post(1),
        criar_post(2),
    ]

    chamadas: list[str] = []

    def fake_search_all_posts(
        keyword,
        **kwargs,
    ):

        chamadas.append(keyword)

        return posts

    monkeypatch.setattr(
        cli,
        "search_all_posts",
        fake_search_all_posts,
        raising=False,
    )

    monkeypatch.setattr(
        cli,
        "parse_post",
        parse_post_real,
        raising=False,
    )

    codigo = main(
        [
            "buscar",
            "tecnologia",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert codigo == 0

    assert chamadas == ["tecnologia"]

    arquivo_saida = tmp_path / "busca_tecnologia.json"

    assert arquivo_saida.exists()

    dados = json.loads(arquivo_saida.read_text(encoding="utf-8"))

    assert isinstance(
        dados,
        list,
    )

    assert len(dados) == 2

    assert dados[0]["id"] == posts[0]["photo_id_str"]

    assert dados[0]["texto"] == "Post 1"

    assert dados[0]["autor"]["usuario"] == "Perfil Teste"

    assert dados[0]["engajamento"]["curtidas"] == 101


def test_cli_perfil_coleta_posts_normalizados(
    monkeypatch,
    tmp_path,
):

    posts = [
        criar_post(1),
        criar_post(2),
        criar_post(3),
    ]

    usuarios_consultados: list[str] = []

    def fake_get_all_profile_posts(
        user_id,
        **kwargs,
    ):

        usuarios_consultados.append(user_id)

        return posts

    monkeypatch.setattr(
        cli,
        "get_all_profile_posts",
        fake_get_all_profile_posts,
    )

    monkeypatch.setattr(
        cli,
        "parse_post",
        parse_post_real,
        raising=False,
    )

    codigo = main(
        [
            "perfil",
            "@perfil_teste",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert codigo == 0

    assert usuarios_consultados == ["@perfil_teste"]

    arquivo_saida = tmp_path / "perfil_teste_posts.json"

    assert arquivo_saida.exists()

    dados = json.loads(arquivo_saida.read_text(encoding="utf-8"))

    assert isinstance(
        dados,
        list,
    )

    assert len(dados) == 3

    assert dados[0]["id"] == posts[0]["photo_id_str"]

    assert dados[0]["url"].endswith(str(posts[0]["photo_id_str"]))

    assert dados[0]["autor"]["id"] == "123456"

    assert dados[0]["engajamento"]["comentarios"] == 30


def test_cli_comentarios_coleta_e_normaliza(
    monkeypatch,
    tmp_path,
):

    monkeypatch.setenv(
        "KWAI_DID",
        "did_teste",
    )

    monkeypatch.setenv(
        "KWAI_EGID",
        "DFPAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    )

    photo_id = "5253599077813406650"

    postagem_url = f"https://www.kwai.com/@perfil_teste/video/{photo_id}"

    comentarios_brutos = [
        {
            "commentId": "1001",
            "userName": "Usuario Um",
            "userId": "5001",
            "kwaiid": "usuario_um",
            "content": "Primeiro comentário",
            "commentLikeCount": 10,
            "commentTime": ("2026-09-14T12:00:00Z"),
        },
        {
            "commentId": "1002",
            "userName": "Usuario Dois",
            "userId": "5002",
            "kwaiid": "usuario_dois",
            "content": "Segundo comentário",
            "commentLikeCount": 20,
            "commentTime": ("2026-09-14T13:00:00Z"),
        },
    ]

    photo_ids_consultados: list[str] = []

    def fake_get_tiny_comments(
        photo_id,
        query_params=None,
        debug=False,
    ):

        photo_ids_consultados.append(photo_id)

        return comentarios_brutos

    monkeypatch.setattr(
        cli,
        "get_tiny_comments",
        fake_get_tiny_comments,
    )

    monkeypatch.setattr(
        cli,
        "parse_comment",
        parse_comment_real,
        raising=False,
    )

    codigo = main(
        [
            "comentarios",
            postagem_url,
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert codigo == 0

    assert photo_ids_consultados == [photo_id]

    arquivo_saida = tmp_path / f"{photo_id}_comentarios.json"

    assert arquivo_saida.exists()

    dados = json.loads(arquivo_saida.read_text(encoding="utf-8"))

    assert isinstance(
        dados,
        list,
    )

    assert len(dados) == 2

    assert dados[0]["id"] == "1001"

    assert dados[0]["postagem_url"] == postagem_url

    assert dados[0]["autor"]["usuario"] == "Usuario Um"

    assert dados[0]["texto"] == "Primeiro comentário"

    assert dados[0]["curtidas"] == 10


@pytest.mark.parametrize(
    "max_comments",
    [25],
)
def test_cli_comentarios_mobile_para_limite_maior_que_tiny(
    monkeypatch,
    tmp_path,
    max_comments,
):

    photo_id = "5253599077813406650"

    postagem_url = f"https://www.kwai.com/@perfil_teste/video/{photo_id}"

    chamadas: dict[str, object] = {}

    def fake_request_provider(**kwargs):

        return object()

    monkeypatch.setattr(
        cli,
        "criar_mobile_request_provider",
        fake_request_provider,
    )

    def fake_get_tiny_comments(
        *args,
        **kwargs,
    ):

        raise AssertionError(
            "Tiny não deveria ser usado quando o fluxo mobile está selecionado."
        )

    class FakeMobileCommentProvider:
        def get_comments(
            self,
            postagem_url_recebida,
            max_comments=None,
            *,
            user_id=None,
        ):

            chamadas["postagem_url"] = postagem_url_recebida

            chamadas["max_comments"] = max_comments

            chamadas["user_id"] = user_id

            return [
                parse_comment_real(
                    {
                        "commentId": str(1000 + indice),
                        "userName": f"Usuario {indice}",
                        "userId": str(5000 + indice),
                        "kwaiid": f"usuario_{indice}",
                        "content": f"Comentario {indice}",
                        "commentLikeCount": indice,
                        "commentTime": "2026-09-14T12:00:00Z",
                    },
                    postagem_url_recebida,
                )
                for indice in range(max_comments or 0)
            ]

    monkeypatch.setattr(
        cli,
        "get_tiny_comments",
        fake_get_tiny_comments,
    )

    monkeypatch.setattr(
        cli,
        "MobileCommentProvider",
        FakeMobileCommentProvider,
        raising=False,
    )

    codigo = main(
        [
            "comentarios",
            postagem_url,
            "--max-comments",
            str(max_comments),
            "--user-id",
            "perfil_teste",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert codigo == 0

    assert chamadas["postagem_url"] == postagem_url

    assert chamadas["max_comments"] == 25

    assert chamadas["user_id"] == "perfil_teste"


def test_cli_coletar_small_limit_uses_tiny(
    monkeypatch,
    tmp_path,
):
    post = criar_post(1)
    chamadas: list[str] = []

    monkeypatch.setattr(
        cli,
        "get_all_profile_posts",
        lambda *args, **kwargs: [post],
    )

    monkeypatch.setattr(
        cli,
        "get_post_details",
        lambda *args, **kwargs: {
            "photo_id": post["photo_id_str"],
        },
    )

    def fake_get_tiny_comments(
        *args,
        **kwargs,
    ):
        chamadas.append(str(kwargs["photo_id"]))

        return [
            {
                "commentId": "1",
                "userName": "Synthetic User",
                "userId": "123",
                "kwaiid": "synthetic_user",
                "content": "Synthetic comment",
                "commentLikeCount": 0,
                "commentTime": "2026-09-14T12:00:00Z",
            }
        ]

    class FailMobileCommentProvider:
        def __init__(self):
            raise AssertionError(
                "O fluxo mobile não deveria ser usado para um limite pequeno."
            )

    monkeypatch.setattr(
        cli,
        "get_tiny_comments",
        fake_get_tiny_comments,
    )

    monkeypatch.setattr(
        cli,
        "MobileCommentProvider",
        FailMobileCommentProvider,
    )

    result = main(
        [
            "coletar",
            "@perfil_teste",
            "--max-comments",
            "10",
            "--output-dir",
            str(tmp_path),
            "--delay",
            "0",
        ]
    )

    assert result == 0
    assert chamadas == [post["photo_id_str"]]

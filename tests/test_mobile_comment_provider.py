import json

from kwai_collector.providers.mobile_comment_provider import (
    MobileCommentProvider,
)


def test_mobile_comment_provider_lê_uma_pagina(
    tmp_path,
):
    arquivo = tmp_path / "mobile.json"

    arquivo.write_text(
        json.dumps(
            {
                "rootComments": [
                    {
                        "comment_id": "1",
                        "author_name": "usuario_1",
                        "author_id": "100",
                        "content": "Primeiro comentario",
                        "liked_count": 5,
                        "timestamp": 1756386002889,
                    },
                    {
                        "comment_id": "2",
                        "author_name": "usuario_2",
                        "author_id": "200",
                        "content": "Segundo comentario",
                        "liked_count": 10,
                        "timestamp": 1756386002889,
                    },
                ],
                "pcursor": "no_more",
            }
        ),
        encoding="utf-8",
    )

    provider = MobileCommentProvider(
        arquivo_json=arquivo,
    )

    comentarios = provider.get_comments("https://www.kwai.com/@teste/video/123")

    assert len(comentarios) == 2
    assert comentarios[0].id == "1"
    assert comentarios[0].autor.usuario == "usuario_1"
    assert comentarios[0].autor.id == "100"
    assert comentarios[0].texto == "Primeiro comentario"
    assert comentarios[0].curtidas == 5

    assert comentarios[1].id == "2"
    assert comentarios[1].texto == "Segundo comentario"


def test_mobile_comment_provider_lê_varias_paginas(
    tmp_path,
):
    arquivo = tmp_path / "mobile.json"

    arquivo.write_text(
        json.dumps(
            [
                {
                    "rootComments": [
                        {
                            "comment_id": "1",
                            "author_name": "usuario_1",
                            "author_id": "100",
                            "content": "Comentario 1",
                            "liked_count": 1,
                            "timestamp": 1756386002889,
                        }
                    ],
                    "pcursor": "cursor_1",
                },
                {
                    "rootComments": [
                        {
                            "comment_id": "2",
                            "author_name": "usuario_2",
                            "author_id": "200",
                            "content": "Comentario 2",
                            "liked_count": 2,
                            "timestamp": 1756386002889,
                        }
                    ],
                    "pcursor": "no_more",
                },
            ]
        ),
        encoding="utf-8",
    )

    provider = MobileCommentProvider(
        arquivo_json=arquivo,
    )

    comentarios = provider.get_comments("https://www.kwai.com/@teste/video/123")

    assert [comentario.id for comentario in comentarios] == [
        "1",
        "2",
    ]


def test_mobile_comment_provider_deduplica_comentarios(
    tmp_path,
):
    arquivo = tmp_path / "mobile.json"

    arquivo.write_text(
        json.dumps(
            [
                {
                    "rootComments": [
                        {
                            "comment_id": "1",
                            "author_name": "usuario",
                            "author_id": "100",
                            "content": "Comentario",
                            "liked_count": 1,
                            "timestamp": 1756386002889,
                        }
                    ],
                    "pcursor": "cursor_1",
                },
                {
                    "rootComments": [
                        {
                            "comment_id": "1",
                            "author_name": "usuario",
                            "author_id": "100",
                            "content": "Comentario",
                            "liked_count": 1,
                            "timestamp": 1756386002889,
                        },
                        {
                            "comment_id": "2",
                            "author_name": "outro",
                            "author_id": "200",
                            "content": "Novo comentario",
                            "liked_count": 2,
                            "timestamp": 1756386002889,
                        },
                    ],
                    "pcursor": "no_more",
                },
            ]
        ),
        encoding="utf-8",
    )

    provider = MobileCommentProvider(
        arquivo_json=arquivo,
    )

    comentarios = provider.get_comments("https://www.kwai.com/@teste/video/123")

    assert [comentario.id for comentario in comentarios] == [
        "1",
        "2",
    ]

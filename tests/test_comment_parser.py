from kwai_collector.models.comentario import Comentario
from kwai_collector.parsers.comment_parser import parse_comment


def test_parse_comment_retorna_comentario():
    comentario_bruto = {
        "commentId": "123456789",
        "userName": "usuario_teste",
        "kwaiid": "987654321",
        "content": "Este é um comentário de teste.",
        "commentLikeCount": 10,
        "commentTime": "2024-06-01T12:34:56Z",
    }
    postagem_url = "https://www.kwai.com/@teste/video/123456789"

    comentario = parse_comment(comentario_bruto, postagem_url)

    assert isinstance(comentario, Comentario)
    assert comentario.id == "123456789"
    assert comentario.postagem_url == postagem_url
    assert comentario.autor.usuario == "usuario_teste"
    assert comentario.autor.id == "987654321"
    assert comentario.texto == "Este é um comentário de teste."
    assert comentario.curtidas == 10


def test_parse_comment_mobile_retorna_comentario():
    comentario_bruto = {
        "comment_id": "182003031691232109",
        "author_name": "usuario_mobile",
        "author_id": "150001553143947",
        "user_id": "150001630602075",
        "content": "Onde assistir",
        "liked_count": 331,
        "timestamp": 1756386002889,
    }

    postagem_url = "https://www.kwai.com/video/123456789"

    comentario = parse_comment(
        comentario_bruto,
        postagem_url,
    )

    assert isinstance(comentario, Comentario)
    assert comentario.id == "182003031691232109"
    assert comentario.postagem_url == postagem_url
    assert comentario.autor.usuario == "usuario_mobile"
    assert comentario.autor.id == "150001553143947"
    assert comentario.texto == "Onde assistir"
    assert comentario.curtidas == 331
    assert comentario.data is not None

"""A1_Radar."""

from datetime import UTC, datetime
from typing import Any

from kwai_collector.models.postagem import Postagem


def parse_post(post: dict[str, Any]) -> Postagem:
    kwai_id = post.get("kwai_id")
    photo_id = post.get("photo_id_str")
    if kwai_id and photo_id:
        url_post = f"https://www.kwai.com/@{kwai_id}/video/{photo_id}"
    else:
        url_post = None
    if kwai_id:
        url_perfil = f"https://www.kwai.com/@{kwai_id}"
    else:
        url_perfil = None
    data_bruta = post.get("time")
    if data_bruta:
        data_convertida = datetime.strptime(  # noqa: DTZ007
            data_bruta,
            "%Y-%m-%d %H:%M:%S",
        )
        data_iso = data_convertida.isoformat()
    else:
        data_iso = None
    coletado_em = datetime.now(UTC).isoformat()
    post_extraido = {
        "id": post.get("photo_id_str"),
        "url": url_post,
        "autor": {
            "usuario": post.get("user_name"),
            "id": post.get("user_id_str"),
            "url_perfil": url_perfil,
        },
        "texto": post.get("caption"),
        "data_publicacao": data_iso,
        "engajamento": {
            "curtidas": post.get("like_count"),
            "comentarios": post.get("comment_count"),
            "compartilhamentos": post.get("forward_count"),
            "visualizacoes": post.get("view_count"),
        },
        "coletado_em": coletado_em,
    }
    return Postagem.model_validate(post_extraido)

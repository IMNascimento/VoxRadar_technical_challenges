"""A1_Radar."""

import logging
from collections.abc import Callable
from typing import Any

from kwai_collector.models.comentario import Comentario
from kwai_collector.models.postagem import Postagem

PostParser = Callable[
    [dict[str, Any]],
    Postagem,
]

CommentParser = Callable[
    [dict[str, Any], str],
    Comentario,
]


def normalizar_posts_com_parser(
    posts: list[dict[str, Any]],
    parser: PostParser,
    logger: logging.Logger,
) -> list[dict[str, Any]]:
    resultados: list[dict[str, Any]] = []

    for post in posts:
        try:
            postagem = parser(post)

        except ValueError as exc:
            logger.warning(
                "Post ignorado por não atender ao schema: %s",
                exc,
            )
            continue

        resultados.append(
            postagem.model_dump(
                mode="json",
            )
        )

    return resultados


def normalizar_comentarios_com_parser(
    comentarios: list[dict[str, Any]],
    postagem_url: str,
    parser: CommentParser,
    logger: logging.Logger,
) -> list[dict[str, Any]]:
    resultados: list[dict[str, Any]] = []

    for comentario in comentarios:
        try:
            comentario_modelo = parser(
                comentario,
                postagem_url,
            )

        except ValueError as exc:
            logger.warning(
                "Comentário ignorado por não atender ao schema: %s",
                exc,
            )
            continue

        resultados.append(
            comentario_modelo.model_dump(
                mode="json",
            )
        )

    return resultados

"""A1_Radar."""

from datetime import UTC, datetime
from typing import Any

from kwai_collector.models.comentario import Comentario


def _parse_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None

    if isinstance(value, datetime):
        return value

    if isinstance(value, (int, float)):
        timestamp = float(value)

        if timestamp > 10_000_000_000:
            timestamp /= 1000

        try:
            return datetime.fromtimestamp(timestamp, tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None

    if isinstance(value, str):
        text = value.strip()

        if not text:
            return None

        if text.isdigit():
            return _parse_datetime(int(text))

        try:
            parsed = datetime.fromisoformat(text)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)

            return parsed
        except ValueError:
            return None

    return None


def parse_comment(
    comentario: dict[str, Any],
    postagem_url: str,
) -> Comentario:
    comment_id = comentario.get("commentId")

    if comment_id is None:
        comment_id = comentario.get("comment_id")

    autor_usuario = comentario.get("userName")

    if autor_usuario is None:
        autor_usuario = comentario.get("author_name")

    autor_id = comentario.get("kwaiid")

    if autor_id is None:
        autor_id = comentario.get("author_id")

    if autor_id is None:
        autor_id = comentario.get("user_id")

    curtidas = comentario.get("commentLikeCount")

    if curtidas is None:
        curtidas = comentario.get("liked_count")

    data = comentario.get("commentTime")

    if data is None:
        data = comentario.get("timestamp")

    comentario_extraido = {
        "id": str(comment_id) if comment_id is not None else None,
        "postagem_url": postagem_url,
        "autor": {
            "usuario": (str(autor_usuario) if autor_usuario is not None else None),
            "id": str(autor_id) if autor_id is not None else None,
        },
        "texto": comentario.get("content"),
        "curtidas": curtidas,
        "data": _parse_datetime(data),
        "coletado_em": datetime.now(UTC),
    }

    return Comentario.model_validate(comentario_extraido)


def parse_ui_comment(
    autor: str | None,
    texto: str,
    curtidas: str | None,
    data: str | None,
    postagem_url: str,
) -> Comentario:
    data_convertida = None

    if data:
        try:
            data_convertida = datetime.strptime(
                data,
                "%d-%m-%Y",
            ).replace(tzinfo=UTC)
        except ValueError:
            data_convertida = None

    curtidas_convertidas = None

    if curtidas and curtidas.isdigit():
        curtidas_convertidas = int(curtidas)

    comentario_extraido = {
        "id": None,
        "postagem_url": postagem_url,
        "autor": {
            "usuario": autor,
            "id": None,
        },
        "texto": texto,
        "curtidas": curtidas_convertidas,
        "data": data_convertida,
        "coletado_em": datetime.now(UTC),
    }

    return Comentario.model_validate(comentario_extraido)

"""Save comment pagination progress without saving request authentication.

A1_Radar.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from kwai_collector.clients.comment_collection_progress import CommentCollectionProgress

_FIELDS = {"version", "photo_id", "user_id", "llsid", "pcursor", "comments", "complete"}


def _decode_checkpoint(data: Any) -> CommentCollectionProgress:
    if not isinstance(data, dict) or set(data) != _FIELDS:
        raise ValueError("O arquivo de progresso possui campos inválidos ou ausentes.")
    if type(data["version"]) is not int or data["version"] != 1:
        raise ValueError("A versão do arquivo de progresso não é suportada.")
    for field in ("photo_id", "user_id", "llsid"):
        if not isinstance(data[field], str) or not data[field].strip():
            raise ValueError(f"O campo {field} do arquivo de progresso é inválido.")
    if not isinstance(data["pcursor"], str):
        # Loading malformed persisted data consistently raises ValueError.
        raise ValueError("O cursor do arquivo de progresso é inválido.")  # noqa: TRY004
    if type(data["complete"]) is not bool:
        raise ValueError("O estado de conclusão do arquivo de progresso é inválido.")
    comments = data["comments"]
    if not isinstance(comments, list) or not all(
        isinstance(comment, dict) for comment in comments
    ):
        raise ValueError("A lista de comentários do arquivo de progresso é inválida.")
    return CommentCollectionProgress(
        photo_id=data["photo_id"],
        user_id=data["user_id"],
        llsid=data["llsid"],
        pcursor=data["pcursor"],
        comments=[dict(comment) for comment in comments],
        complete=data["complete"],
    )


def load_comment_checkpoint(path: Path) -> CommentCollectionProgress:
    """Read validated progress; errors never include saved contents."""
    try:
        source = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ValueError(
            "Não existe progresso salvo para retomar esta coleta."
        ) from exc
    except (OSError, UnicodeError) as exc:
        raise ValueError(
            "Não foi possível ler o arquivo de progresso informado."
        ) from exc
    try:
        data = json.loads(source)
    except (ValueError, RecursionError) as exc:
        raise ValueError("O arquivo de progresso não contém JSON válido.") from exc
    return _decode_checkpoint(data)


def save_comment_checkpoint(progress: CommentCollectionProgress, path: Path) -> None:
    """Replace the checkpoint atomically using a temporary file beside it."""
    data = {
        "version": 1,
        "photo_id": progress.photo_id,
        "user_id": progress.user_id,
        "llsid": progress.llsid,
        "pcursor": progress.pcursor,
        "comments": progress.comments,
        "complete": progress.complete,
    }
    _decode_checkpoint(data)
    try:
        source = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    except (TypeError, ValueError, RecursionError) as exc:
        raise ValueError("O progresso da coleta não pode ser salvo em JSON.") from exc

    temporary_path: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(source)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    except OSError as exc:
        raise ValueError("Não foi possível salvar o progresso da coleta.") from exc
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

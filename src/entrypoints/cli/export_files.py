"""Layout de diretórios e escrita atômica dos JSON exportados pela CLI.

Cada execução ganha uma pasta própria em ``<base>/<dono>/<carimbo UTC>-<sufixo>``.
Postagens vão em ``posts.json``; comentários em ``<kind>/<photo_id>.json``. Uma
etapa que falhou com parcial grava ``.partial.json``; sem itens, não grava nada.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from ...application.dtos.collection_result import CollectionResult
from ...domain.entities.comment import Comment
from ...domain.entities.post import Post
from ...shared.logging.logging_config import get_logger

logger = get_logger("cli")
_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def _safe_name(value: str) -> str:
    """Converte o valor em nome de arquivo seguro, com hash quando o nome muda."""
    name = re.sub(r"[^a-zA-Z0-9_.-]", "_", value).strip(".")[:80]
    if not name or name.split(".")[0].upper() in _RESERVED_NAMES:
        name = f"_{name}"
    if name != value:
        name += "-" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
    return name


def create_export_directory(base: Path, owner: str) -> Path:
    """Cria o diretório exclusivo de uma execução, com nomes seguros no Windows.

    Args:
        base: diretório base da exportação.
        owner: dono da coleta (handle, ``search`` ou ``post-<id>``); caracteres
            inválidos e nomes reservados do Windows são neutralizados.

    Returns:
        O caminho do diretório criado para esta execução.
    """
    parent = base / _safe_name(owner)
    parent.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid4().hex[:8]
    run = parent / run_id
    run.mkdir()
    return run


def write_export(run: Path, result: CollectionResult[Post | Comment]) -> Path | None:
    """Grava os itens de um resultado em JSON de forma atômica (temporário + rename).

    Args:
        run: diretório da execução.
        result: resultado a gravar; com ``error``, o parcial vai em ``.partial.json``.

    Returns:
        O caminho gravado, ou ``None`` quando a etapa falhou sem itens.
    """
    if result.error is not None and not result.items:
        return None
    stem = "posts" if result.post is None else result.post.photo_id.value
    suffix = ".partial.json" if result.error is not None else ".json"
    folder = run if result.kind == "posts" else run / result.kind
    target = folder / f"{stem}{suffix}"
    folder.mkdir(parents=True, exist_ok=True)
    text = json.dumps([asdict(item) for item in result.items], ensure_ascii=False, indent=2)
    temporary = folder / f"{target.name}.{uuid4().hex}.tmp"
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            stream.write(text + "\n")
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    logger.info("%d record(s) saved to %s", len(result.items), target)
    return target

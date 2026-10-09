"""Resultado de uma unidade de coleta, separado de sua apresentação em JSON."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

from ..domain.exceptions import KwaiCollectorError

CollectionKind = Literal["posts", "comments", "comments-replies"]
CollectionStage = Literal["posts", "roots", "replies"]


@dataclass(frozen=True)
class CollectionResult:
    """Itens e falha explícita da etapa; vazio sem erro é sucesso válido."""

    kind: CollectionKind
    items: tuple[BaseModel, ...]
    stage: CollectionStage
    post_url: str | None = None
    error: KwaiCollectorError | None = None

"""Composição da aplicação (*composition root*).

Único módulo fora de ``infrastructure/`` que conhece os adapters concretos:
monta os três casos de uso com as portas implementadas e expõe ``close()`` para
encerrar as sessões HTTP.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from types import TracebackType
from typing import Protocol

from .application.collect_comments import CollectComments
from .application.collect_user_posts import CollectUserPosts
from .application.search_posts import SearchPosts
from .config import Settings
from .infrastructure.mobile_client import MobileApiAdapter
from .infrastructure.web_client import KwaiWebAdapter


class Closeable(Protocol):
    """Recurso com encerramento explícito (ex.: sessão HTTP)."""

    def close(self) -> None:
        """Encerra o recurso."""
        ...


@dataclass
class Services:
    """Casos de uso compostos e os recursos de rede a encerrar.

    O uso normal é via ``search_posts``/``user_posts``/``comments``; os
    recursos concretos ficam encapsulados em ``_closeables`` para o ``close()``.
    """

    search_posts: SearchPosts
    user_posts: CollectUserPosts
    comments: CollectComments
    _closeables: tuple[Closeable, ...] = field(repr=False)

    def close(self) -> None:
        """Encerra todos os recursos de rede, mesmo que um deles falhe."""
        with contextlib.ExitStack() as stack:
            for resource in self._closeables:
                stack.callback(resource.close)

    def __enter__(self) -> Services:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()


def build_services(settings: Settings) -> Services:
    """Monta os casos de uso com os adapters concretos.

    Args:
        settings: configuração do coletor (timeout, retry, delay e UA).

    Returns:
        Os serviços prontos para uso e para ``close()``.
    """
    web_api = KwaiWebAdapter(settings)
    mobile_api = MobileApiAdapter(settings)
    return Services(
        search_posts=SearchPosts(web_api),
        user_posts=CollectUserPosts(mobile_api),
        comments=CollectComments(mobile_api),
        _closeables=(web_api, mobile_api),
    )

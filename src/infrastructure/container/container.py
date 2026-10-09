"""Composição da aplicação (*composition root*).

Único lugar que instancia a infraestrutura concreta: cria os clientes do Kwai
(donos das sessões HTTP), os adapters que implementam as portas e o relógio,
monta os casos de uso e expõe ``close()`` para encerrar as sessões.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from types import TracebackType
from typing import Protocol

from ...application.use_cases.collect_comment_versions import CollectCommentVersions
from ...application.use_cases.collect_profile_bundle import CollectProfileBundle
from ...application.use_cases.search_posts import SearchPosts
from ...config.settings import Settings
from ..clock.system_clock import SystemClock
from ..kwai.mobile.adapter import MobileApiAdapter
from ..kwai.mobile.client import MobileApiClient
from ..kwai.web.adapter import KwaiWebAdapter
from ..kwai.web.client import KwaiWebClient


class Closeable(Protocol):
    """Recurso com encerramento explícito (ex.: sessão HTTP)."""

    def close(self) -> None:
        """Encerra o recurso."""
        ...


@dataclass(frozen=True)
class Services:
    """Casos de uso compostos e os recursos de rede a encerrar.

    O uso normal é pelos casos de uso expostos como atributos; os
    recursos concretos ficam encapsulados em ``_closeables`` para o ``close()``.
    """

    search_posts: SearchPosts
    comment_versions: CollectCommentVersions
    profile_bundle: CollectProfileBundle
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
    """Monta os casos de uso com os clientes, adapters e relógio concretos.

    Args:
        settings: configuração do coletor (timeout, retry, delay e UA).

    Returns:
        Os serviços prontos para uso e para ``close()``.
    """
    web_client = KwaiWebClient(settings)
    mobile_client = MobileApiClient(settings)
    web_api = KwaiWebAdapter(web_client)
    mobile_api = MobileApiAdapter(mobile_client)
    clock = SystemClock()
    return Services(
        search_posts=SearchPosts(web_api, clock),
        comment_versions=CollectCommentVersions(mobile_api, clock),
        profile_bundle=CollectProfileBundle(mobile_api, mobile_api, clock),
        _closeables=(web_client, mobile_client),
    )

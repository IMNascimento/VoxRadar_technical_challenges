"""Caso de uso: postagens de um usuário a partir do SSR do perfil."""

from __future__ import annotations

from ..domain.identity import normalize_handle, post_dedup_key
from ..domain.value_objects.iso_timestamp import IsoTimestamp
from ..shared.logging_config import COLLECTOR_LOGGER_NAME, get_logger
from ..shared.utils.timestamps import now_iso
from .models import Postagem
from .ports import ProfileApiPort

logger = get_logger(COLLECTOR_LOGGER_NAME)


class CollectUserPosts:
    """Coleta as postagens de um usuário a partir do estado SSR do perfil."""

    def __init__(self, api: ProfileApiPort) -> None:
        """Inicializa o caso de uso.

        Args:
            api: porta de leitura do perfil na API web do Kwai.
        """
        self._api = api

    def execute(self, user: str, *, limit: int | None = None) -> list[Postagem]:
        """Coleta o SSR do perfil, deduplicando e respeitando o limite.

        Args:
            user: conta do usuário (ex.: ``@perfil`` ou ``perfil``).
            limit: teto opcional de postagens **únicas**.

        Returns:
            As postagens únicas, na ordem do SSR.

        Raises:
            InvalidInputError: se a conta for inválida.
        """
        handle = normalize_handle(user)
        logger.info("coletando postagens de @%s", handle.value)
        collected_at = IsoTimestamp(now_iso())
        posts = self._api.profile_posts(handle, collected_at=collected_at)
        unique: list[Postagem] = []
        seen: set[str] = set()
        for post in posts:
            key = post_dedup_key(post.id, post.url)
            if key in seen:
                continue
            seen.add(key)
            unique.append(post)
            if limit is not None and len(unique) >= limit:
                break
        logger.info("usuário @%s: %d postagens coletadas", handle.value, len(unique))
        return unique

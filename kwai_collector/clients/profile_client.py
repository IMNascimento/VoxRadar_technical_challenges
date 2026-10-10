"""A1_Radar."""

from __future__ import annotations

import logging
import time
from typing import Any, Final

import httpx

from kwai_collector.config import settings

logger = logging.getLogger(__name__)


PROFILE_FEED_URL: Final = "https://www.kwai.com/rest/o/w/pc/feed/profile"

PROFILE_PAGE_SIZE: Final = 20

HTTP_TOO_MANY_REQUESTS: Final = 429
HTTP_SERVER_ERROR_MIN: Final = 500


def _calcular_backoff(
    tentativa: int,
    backoff_base: float,
) -> float:
    return backoff_base * (2 ** (tentativa - 1))


def _deve_repetir_request(
    status_code: int,
) -> bool:
    return status_code == HTTP_TOO_MANY_REQUESTS or status_code >= HTTP_SERVER_ERROR_MIN


def get_profile_page(
    user_id: str,
    pcursor: str = "",
    max_tentativas: int = settings.max_tentativas,
    backoff_base: float = settings.backoff_base,
) -> tuple[
    list[dict[str, Any]],
    str | None,
]:
    payload = {
        "beforePage": "",
        "count": PROFILE_PAGE_SIZE,
        "fromPage": "PC_PROFILE",
        "pcursor": pcursor,
        "userId": user_id,
    }

    headers = {
        "Content-Type": "application/json",
        "accept": ("application/json, text/plain, */*"),
    }

    for tentativa in range(
        1,
        max_tentativas + 1,
    ):
        try:
            response = httpx.post(
                PROFILE_FEED_URL,
                json=payload,
                headers=headers,
            )

        except httpx.RequestError:
            if tentativa == max_tentativas:
                raise

            espera = _calcular_backoff(
                tentativa,
                backoff_base,
            )

            logger.warning(
                "Erro de conexão. Nova tentativa em %.1fs.",
                espera,
            )

            time.sleep(espera)

            continue

        if _deve_repetir_request(response.status_code):
            if tentativa == max_tentativas:
                response.raise_for_status()

            espera = _calcular_backoff(
                tentativa,
                backoff_base,
            )

            logger.warning(
                "Kwai respondeu HTTP %d. Nova tentativa em %.1fs.",
                response.status_code,
                espera,
            )

            time.sleep(espera)

            continue

        response.raise_for_status()

        dados = response.json()

        feeds_raw = dados.get(
            "feeds",
            [],
        )

        cursor_raw = dados.get("cursor")

        feeds: list[dict[str, Any]] = (
            feeds_raw
            if isinstance(
                feeds_raw,
                list,
            )
            else []
        )

        cursor = str(cursor_raw) if cursor_raw is not None else None

        return (
            feeds,
            cursor,
        )

    raise RuntimeError("Não foi possível obter a página do perfil.")


def get_all_profile_posts(
    user_id: str,
    max_paginas: int | None = None,
    delay: float = settings.delay,
) -> list[dict[str, Any]]:
    if max_paginas is not None and max_paginas <= 0:
        return []

    resultados: list[dict[str, Any]] = []

    ids_vistos: set[str] = set()
    cursores_vistos: set[str] = set()

    pcursor = ""
    pagina = 0

    while max_paginas is None or pagina < max_paginas:
        if pagina > 0 and delay > 0:
            time.sleep(delay)

        feeds, novo_cursor = get_profile_page(
            user_id=user_id,
            pcursor=pcursor,
        )

        pagina += 1

        if not feeds:
            break

        _adicionar_posts_unicos(
            feeds,
            resultados,
            ids_vistos,
        )

        if not novo_cursor:
            break

        if novo_cursor == pcursor:
            logger.warning("Paginação encerrada porque o cursor não avançou.")
            break

        if novo_cursor in cursores_vistos:
            logger.warning("Paginação encerrada porque um cursor foi repetido.")
            break

        cursores_vistos.add(novo_cursor)

        pcursor = novo_cursor

    return resultados


def _adicionar_posts_unicos(
    feeds: list[dict[str, Any]],
    resultados: list[dict[str, Any]],
    ids_vistos: set[str],
) -> None:
    for post in feeds:
        post_id_raw = post.get("photo_id_str")

        if post_id_raw is None:
            resultados.append(post)
            continue

        post_id = str(post_id_raw)

        if post_id in ids_vistos:
            continue

        ids_vistos.add(post_id)

        resultados.append(post)

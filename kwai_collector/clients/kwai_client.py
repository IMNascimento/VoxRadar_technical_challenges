"""A1_Radar."""

import logging
import time
from typing import Any

import httpx

from kwai_collector.config import settings

logger = logging.getLogger(__name__)


def search_posts(
    keyword: str,
    pcursor: int = 0,
    max_tentativas: int = settings.max_tentativas,
    backoff_base: float = settings.backoff_base,
) -> list[dict[str, Any]]:
    url = "https://www.kwai.com/rest/o/w/pwa/v2/search/word/outer"

    payload = {
        "searchWord": keyword,
        "count": 10,
        "fromUser": False,
        "mobile": True,
        "need_ld_json": False,
        "need_tdk": False,
        "pcursor": pcursor,
        "request_source": 1102,
        "seoDefaultFilterV2": True,
        "url": "https://www.kwai.com/discover",
        "ai_content": False,
    }

    headers = {
        "Content-Type": "application/json",
        "accept": "application/json, text/plain, */*",
    }

    for tentativa in range(max_tentativas):
        try:
            response = httpx.post(
                url,
                json=payload,
                headers=headers,
            )

            response.raise_for_status()
            break

        except (httpx.RequestError, httpx.HTTPStatusError) as erro:
            if isinstance(erro, httpx.HTTPStatusError):
                status_code = erro.response.status_code

                if status_code != 429 and not 500 <= status_code < 600:
                    raise

            logger.warning(
                "Erro na tentativa %d/%d: %s",
                tentativa + 1,
                max_tentativas,
                erro,
            )

            if tentativa == max_tentativas - 1:
                raise

            tempo_espera = backoff_base * (2**tentativa)
            time.sleep(tempo_espera)

    dados = response.json()

    feeds = dados.get("feeds", [])

    return feeds


def search_all_posts(
    keyword: str,
    max_paginas: int = 5,
    delay: float = settings.delay,
) -> list[dict[str, Any]]:
    resultados: list[dict[str, Any]] = []
    ids_encontrados: set[str] = set()

    for pcursor in range(max_paginas):
        if pcursor > 0 and delay > 0:
            time.sleep(delay)

        feeds = search_posts(keyword, pcursor=pcursor)

        if not feeds:
            break

        for post in feeds:
            post_id = post.get("photo_id_str")

            if post_id in ids_encontrados:
                continue

            if post_id is not None:
                ids_encontrados.add(post_id)

            resultados.append(post)

    return resultados

"""A1_Radar."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from kwai_collector.config import settings

logger = logging.getLogger(__name__)


class RealCommentClient:
    def __init__(
        self,
        base_url: str,
        signature_provider: Any,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.signature_provider = signature_provider

        self.client = httpx.Client(
            timeout=20.0,
            follow_redirects=True,
        )

    def post(
        self,
        endpoint: str,
        query: dict[str, str],
        body_data: dict[str, Any],
    ) -> httpx.Response:
        url = f"{self.base_url}{endpoint}"

        body_para_assinatura = {
            str(chave): str(valor) for chave, valor in body_data.items()
        }

        headers_autenticacao = self.signature_provider.sign(
            query,
            body_para_assinatura,
            client_salt=None,
        )

        headers = dict(headers_autenticacao)

        headers.update(
            {
                "Accept": ("application/json, text/plain, */*"),
                "Accept-Language": ("pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7"),
                "Content-Type": ("application/json"),
                "Origin": ("https://www.kwai.com"),
                "Referer": ("https://www.kwai.com/"),
                "User-Agent": (
                    "Mozilla/5.0 "
                    "(Windows NT 10.0; "
                    "Win64; x64) "
                    "AppleWebKit/537.36 "
                    "(KHTML, like Gecko) "
                    "Chrome/152.0.0.0 "
                    "Safari/537.36"
                ),
            }
        )

        if settings.cookie:
            headers["Cookie"] = settings.cookie

        logger.info(
            "HTTP Request: POST %s",
            url,
        )

        logger.debug(
            "Payload: %s",
            body_data,
        )

        return self.client.post(
            url,
            params=query,
            json=body_data,
            headers=headers,
        )

    def fetch_all_comments_paginated(
        self,
        photo_id: str,
        author_id: str,
        max_comments: int = 20,
    ) -> list[dict[str, Any]]:
        comentarios_totais: list[dict[str, Any]] = []

        cursor = ""

        endpoint = "/rest/o/w/pc/getComments/list"

        logger.debug(
            "author_id=%s",
            author_id,
        )

        while len(comentarios_totais) < max_comments:
            quantidade_restante = max_comments - len(comentarios_totais)

            root_comment_count = min(
                10,
                quantidade_restante,
            )

            payload = {
                "photo_id": str(photo_id),
                "cursor": cursor,
                "rootCommentCount": (root_comment_count),
                "subCommentCount": 2,
            }

            response = self.post(
                endpoint,
                {},
                payload,
            )

            logger.debug(
                "Status HTTP: %s",
                response.status_code,
            )

            logger.debug(
                "Content-Type: %s",
                response.headers.get("content-type"),
            )

            logger.debug(
                "X-KsResult: %s",
                response.headers.get("x-ksresult"),
            )

            logger.debug(
                "Resposta bruta: %s",
                response.text[:3000],
            )

            response.raise_for_status()

            try:
                dados = response.json()

            except ValueError as exc:
                raise RuntimeError(
                    "O Kwai retornou uma resposta que nao e JSON."
                ) from exc

            if not isinstance(
                dados,
                dict,
            ):
                raise TypeError("A resposta do Kwai possui formato invalido.")

            result = dados.get("result")

            error_msg = dados.get("error_msg")

            logger.debug(
                "result=%r",
                result,
            )

            logger.debug(
                "error_msg=%r",
                error_msg,
            )

            if result != 1:
                raise RuntimeError(
                    "A API de comentarios "
                    "retornou erro. "
                    f"result={result!r} "
                    f"error_msg={error_msg!r}"
                )

            comentarios_raw = dados.get("rootComments")

            if not isinstance(
                comentarios_raw,
                list,
            ):
                raise TypeError(
                    "Resposta result=1, mas sem rootComments em formato de lista."
                )

            logger.debug(
                "Comentarios nesta pagina: %d",
                len(comentarios_raw),
            )

            for comentario in comentarios_raw:
                if len(comentarios_totais) >= max_comments:
                    break

                if isinstance(
                    comentario,
                    dict,
                ):
                    comentarios_totais.append(comentario)

            novo_cursor = dados.get("cursor")

            logger.debug(
                "cursor retornado: %r",
                novo_cursor,
            )

            if novo_cursor in (
                None,
                "",
                "no_more",
            ):
                break

            novo_cursor_str = str(novo_cursor)

            if novo_cursor_str == cursor:
                logger.warning("O cursor nao mudou; paginacao encerrada.")
                break

            cursor = novo_cursor_str

            time.sleep(1.0)

        return comentarios_totais

import logging
from typing import Any

import httpx

from kwai_collector.clients.comment_client import KwaiCommentsError

logger = logging.getLogger(__name__)

A1_Radar = "A1_Radar"

TINY_BASE_URLS = (
    "https://api.kwai-pro.com",
    "https://api.kwaipros.com",
)

TINY_COMMENTS_ENDPOINT = "/rest/o/lite/comment/list"

DEFAULT_TIMEOUT = 20.0

TINY_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/x-www-form-urlencoded",
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 14; SM-A356E) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/152.0.0.0 Mobile Safari/537.36"
    ),
}


def _registrar_tiny_request(
    url: str,
    query_params: dict[str, str],
    body: dict[str, str],
) -> None:
    campos_sensiveis = {
        "did",
        "egid",
        "sig",
        "__ns_sig3",
        "__ns_sig4",
        "client_key",
        "llsid",
    }

    params_seguros = {
        chave: ("***REDACTED***" if chave.lower() in campos_sensiveis else valor)
        for chave, valor in query_params.items()
    }

    request = httpx.Request(
        "POST",
        url,
        params=params_seguros,
    )

    logger.debug(
        "TINY REQUEST | method=POST | url=%s",
        request.url,
    )

    logger.debug(
        "TINY REQUEST | body_keys=%s",
        sorted(body.keys()),
    )

    logger.debug(
        "TINY REQUEST | query_keys=%s",
        sorted(query_params.keys()),
    )


def _registrar_tiny_response(
    response: httpx.Response,
) -> None:
    logger.debug(
        "TINY RESPONSE | status=%d",
        response.status_code,
    )

    logger.debug(
        "TINY RESPONSE | content_type=%s",
        response.headers.get(
            "content-type",
        ),
    )

    logger.debug(
        "TINY RESPONSE | body=%s",
        response.text,
    )


def get_tiny_comments(
    photo_id: str,
    query_params: dict[str, str],
    *,
    debug: bool = False,
    timeout: float = DEFAULT_TIMEOUT,
) -> list[dict[str, Any]]:
    """
    Coleta comentários pela Tiny API.

    O endpoint retorna normalmente:

        {
            "result": 1,
            "comments": [...]
        }

    Para postagens sem comentários também pode retornar:

        {
            "result": 1
        }

    Nesse caso a função retorna uma lista vazia.
    """

    photo_id = str(photo_id).strip()

    if not photo_id:
        raise KwaiCommentsError("photo_id não pode ser vazio.")

    if not photo_id.isdigit():
        raise KwaiCommentsError("photo_id deve ser numérico.")

    params = {str(chave): str(valor) for chave, valor in query_params.items()}

    body = dict(params)
    body["photo_id"] = photo_id

    ultimo_erro: KwaiCommentsError | None = None

    for base_url in TINY_BASE_URLS:
        url = f"{base_url}{TINY_COMMENTS_ENDPOINT}"

        if debug:
            _registrar_tiny_request(
                url,
                params,
                body,
            )

        try:
            response = httpx.post(
                url,
                params=params,
                data=body,
                headers=TINY_HEADERS,
                timeout=timeout,
                follow_redirects=True,
            )

            if debug:
                _registrar_tiny_response(response)

            response.raise_for_status()

            try:
                data = response.json()

            except ValueError as exc:
                raise KwaiCommentsError(
                    "A Tiny API retornou uma resposta que não é JSON."
                ) from exc

            if not isinstance(
                data,
                dict,
            ):
                raise KwaiCommentsError("A resposta Tiny não é um objeto JSON.")

            result = data.get("result")

            if result not in (
                1,
                "1",
            ):
                raise KwaiCommentsError(
                    "A Tiny API retornou erro. "
                    f"result={result!r} "
                    f"status={data.get('status')!r} "
                    f"message={data.get('message')!r}"
                )

            comments_raw = data.get("comments")

            # {"result": 1} sem "comments"
            # representa uma postagem sem comentários.
            if comments_raw is None:
                return []

            if not isinstance(
                comments_raw,
                list,
            ):
                raise KwaiCommentsError(
                    "O campo 'comments' da resposta Tiny não possui o formato esperado."
                )

            comments: list[dict[str, Any]] = [
                dict(item)
                for item in comments_raw
                if isinstance(
                    item,
                    dict,
                )
            ]

            return comments

        except httpx.HTTPStatusError as exc:
            ultimo_erro = KwaiCommentsError(
                f"Erro HTTP {exc.response.status_code} ao acessar a Tiny API."
            )

        except httpx.RequestError as exc:
            ultimo_erro = KwaiCommentsError(f"Erro de conexão com a Tiny API: {exc}")

        except KwaiCommentsError as exc:
            ultimo_erro = exc

    if ultimo_erro is not None:
        raise ultimo_erro

    raise KwaiCommentsError("Não foi possível consultar a Tiny API.")

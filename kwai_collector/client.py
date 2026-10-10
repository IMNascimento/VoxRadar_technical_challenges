import logging
import time
from collections.abc import Callable
from typing import Any

import httpx

from kwai_collector.config import settings

log = logging.getLogger(__name__)

WEB_URL = "https://www.kwai.com"

WEB_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Origin": WEB_URL,
    "Referer": WEB_URL + "/",
}

# status que vale a pena tentar de novo
RETRY_STATUS = [429, 500, 502, 503, 504]


class KwaiError(Exception):
    pass


class TransientError(Exception):
    # falha passageira, o retry tenta de novo
    pass


_last_request = 0.0


def wait_delay() -> None:
    # espera o intervalo mínimo entre um request e outro
    global _last_request
    wait = settings.request_delay - (time.monotonic() - _last_request)
    if wait > 0:
        time.sleep(wait)
    _last_request = time.monotonic()


def post_json(url: str, **kwargs: Any) -> dict[str, Any]:
    wait_delay()
    log.debug("POST %s", url)
    resp = httpx.post(url, timeout=settings.http_timeout, **kwargs)
    if resp.status_code in RETRY_STATUS:
        raise TransientError(f"status {resp.status_code} em {url}")
    resp.raise_for_status()  # 4xx não adianta repetir
    try:
        data = resp.json()
    except ValueError as e:
        # o servidor pode devolver HTML em vez de JSON
        raise TransientError(f"resposta não é json em {url}") from e
    if not isinstance(data, dict):
        raise TransientError(f"resposta inesperada em {url}")
    return data


def with_retry(func: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    # tenta de novo só em falha passageira, esperando um pouco mais a cada vez
    attempt = 0
    while True:
        try:
            return func()
        except (TransientError, httpx.TransportError) as e:
            if attempt >= settings.max_retries:
                raise KwaiError(f"request falhou: {e}") from e
            log.warning("request falhou (%s), tentando de novo", e)
            time.sleep(min(0.5 * 2**attempt, 8))
            attempt += 1
        except httpx.HTTPStatusError as e:
            raise KwaiError(f"request falhou: {e}") from e


def check_result(data: dict[str, Any], path: str) -> None:
    # o Kwai pode responder HTTP 200 com erro no campo result (1 = ok)
    result = data.get("result")
    if result is not None and result != 1:
        msg = data.get("error_msg") or "erro da api do kwai"
        raise KwaiError(f"{msg} (result={result}) em {path}")


def post_web(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    headers = {**WEB_HEADERS, "User-Agent": settings.user_agent}
    data = with_retry(
        lambda: post_json(WEB_URL + path, json=payload, headers=headers, follow_redirects=True)
    )
    check_result(data, path)
    return data

import hashlib
import logging
import time
import uuid
from collections.abc import Callable
from typing import Any

import httpx

from kwai_collector.config import settings

log = logging.getLogger(__name__)

WEB_URL = "https://www.kwai.com"

# hosts da API móvel, usados nessa ordem
MOBILE_HOSTS = [
    "https://api.kwai-pro.com",
    "https://api1-us.kwai-pro.com",
    "https://api2-us.kwaipros.com",
]

# versão e sal usados no request capturado do Kwai Lite
APP_VERSION = "10.3.20.539600"
CLIENT_KEY = "3c2cd3f3"
SIG_SALT = "382700b563f4"

# parâmetros copiados de um request do app
APP_QUERY = {
    "mod": "Google(sdk_gphone_x86)",
    "appver": APP_VERSION,
    "language": "en-us",
    "lon": "0",
    "lat": "0",
    "sys": "KWAI_ANDROID_11",
    "mcc": "310",
    "pkg": "kwai.lite.video",
    "ud": "0",
    "ds": "-1",
    "vid": "ANDROID_c3d0873a15becaef",
    "egid": "DFPD22BD03C9C5B23E86C144229A62DF3F10B2FD4477ED93B5CEECDCD9DA2F4D",
    "did": "ANDROID_c3d0873a15becaef",
    "oc": "UNKNOWN",
    "net": "WIFI",
    "netScore": "8",
    "countryInfo": "USA",
    "country_code": "us",
    "kwai_tiny_type": "2",
    "time_zone": "GMT GMT",
    "bucket": "usa",
    "app": "1",
    "kpf": "ANDROID_PHONE",
    "ver": "10.3",
    "c": "GOOGLE_PLAY",
    "kpn": "KWAI",
    "abi": "armeabi-v7a",
}

WEB_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Origin": WEB_URL,
    "Referer": WEB_URL + "/",
}
APP_HEADERS = {"User-Agent": "kwai-android", "Accept": "application/json"}

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


def create_signature(params: dict[str, str]) -> str:
    # junta chave=valor em ordem alfabética, sem separador, e calcula MD5 com o sal
    text = ""
    for key in sorted(params):
        if key in ("sig", "__NS_sig3", "__NStokensig"):
            continue
        text += f"{key}={params[key]}"
    return hashlib.md5((text + SIG_SALT).encode("utf-8")).hexdigest()


def build_app_query() -> dict[str, str]:
    query = dict(APP_QUERY)
    query["timestamp"] = str(int(time.time() * 1000))
    query["session_id"] = str(uuid.uuid4())
    return query


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


def post_mobile(path: str, query: dict[str, str], body: dict[str, str]) -> dict[str, Any]:
    body = dict(body)
    body["sig"] = create_signature({**query, **body})

    def try_hosts() -> dict[str, Any]:
        error: Exception | None = None
        transient = False
        for host in MOBILE_HOSTS:
            try:
                return post_json(host + path, params=query, data=body, headers=APP_HEADERS)
            except httpx.HTTPStatusError as e:
                error = e
            except (TransientError, httpx.TransportError) as e:
                error = e
                transient = True
            log.warning("host %s falhou (%s), tentando o próximo", host, error)
        # se houve falha passageira, tenta todos os hosts de novo
        if transient:
            raise TransientError(f"todos os hosts falharam: {error}")
        raise KwaiError(f"todos os hosts falharam: {error}")

    data = with_retry(try_hosts)
    check_result(data, path)
    return data

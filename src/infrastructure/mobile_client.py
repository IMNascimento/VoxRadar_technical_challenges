"""Adapter da API MÓVEL anônima do Kwai (comentários) — 100% Python, sem emulador.

Descoberta (09/2026, validada contra o app real):
    ``POST /rest/o/comment/list/v2`` (API móvel) aceita uma requisição
    **anônima** (sem login, sem cookies) assinada **apenas com o ``sig``** — a
    fórmula e o preimage estão em :mod:`src.shared.utils.signature`.

    O ``__NS_sig3`` **não** é necessário para estes endpoints (verificado: sem
    ele a resposta é ``result: 1`` com os dados) e, quando presente na
    requisição do app, **não** entra no preimage do ``sig`` — o app o adiciona
    depois da assinatura. A assinatura cobre os parâmetros da *query* **e** do
    corpo.

    As respostas (sub-comentários) vêm de ``POST /rest/o/comment/sublist`` com o
    mesmo contexto e a mesma assinatura; o corpo usa ``rootCommentId`` e exige
    ``client_key`` (sem ele o gateway responde ``result: 40``).

Os parâmetros abaixo são o **contexto completo capturado do app** (Kwai Lite
10.3.20.539600) — a configuração da **fonte da verdade** (`kwai-pure`): emula o
app ao máximo (`timestamp`/`session_id` são gerados por requisição, como o app
faz). Existe uma **escada de fallback** documentada: se o gateway endurecer,
o mínimo provado (`kpn` + `appver` no query; `photoId`/`count`/`pcursor`/
`client_key`/`sig` no corpo) é aceito — ver ``docs/solucao_api_movel_anonima.md`` §3.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

import httpx

from ..application.ports import CommentApiPort, CommentPage, RootComment, SubCommentPage
from ..config import Settings
from ..domain.business_result import ensure_business_success
from ..domain.value_objects.cursor import Cursor
from ..domain.value_objects.identifiers import CommentId, PhotoId
from ..domain.value_objects.iso_timestamp import IsoTimestamp
from ..shared.logging_config import get_logger
from ..shared.utils.coercion import as_int_scalar
from ..shared.utils.ratelimit import RateLimiter
from ..shared.utils.signature import compute_sig
from .exceptions import KwaiTransportError, UnexpectedResponseError
from .http_utils import decode_json_dict
from .mapping import parse_comment, parse_sub_comment

logger = get_logger("mobile")

COMMENT_HOST = "https://api.kwai-pro.com"
COMMENT_PATH = "/rest/o/comment/list/v2"
SUBLIST_PATH = "/rest/o/comment/sublist"
# Máximo de itens por página aceito pela sublista de respostas.
SUBLIST_MAX_COUNT = 100
# Gateways equivalentes (mesma rota e mesma assinatura); tenta na ordem.
COMMENT_FALLBACK_HOSTS: tuple[str, ...] = (
    "https://api1-us.kwai-pro.com",
    "https://api2-us.kwaipros.com",
)
COMMENT_HOSTS: tuple[str, ...] = (COMMENT_HOST, *COMMENT_FALLBACK_HOSTS)
CLIENT_KEY = "3c2cd3f3"
APP_VERSION = "10.3.20.539600"
# O app usa este UA; a resposta é idêntica sem ele (mantido por fidelidade).
APP_USER_AGENT = "kwai-android"

# Contexto/dispositivo do app (fonte da verdade: `kwai-pure`).
DEFAULT_QUERY: dict[str, str] = {
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

# Corpo enviado pelo app. ``count`` vem por requisição (default 50).
DEFAULT_BODY: dict[str, str] = {
    "order": "desc",
    "photoPageType": "0",
    "requestType": "3",
    "isPreload": "false",
    "preloadSource": "",
    "os": "android",
    "client_key": CLIENT_KEY,
}


class MobileCommentAdapter(CommentApiPort):
    """Acesso HTTP à API móvel de comentários, implementando :class:`CommentApiPort`."""

    def __init__(self, settings: Settings) -> None:
        """Inicializa a sessão httpx anônima.

        Args:
            settings: configuração do coletor (timeout e delay do rate limit).
        """
        self._rate = RateLimiter(settings.request_delay)
        self._client = httpx.Client(
            timeout=settings.http_timeout,
            headers={"User-Agent": APP_USER_AGENT, "Accept": "application/json"},
        )

    def close(self) -> None:
        """Encerra a sessão HTTP."""
        self._client.close()

    def fetch_page(
        self,
        photo_id: PhotoId,
        *,
        cursor: Cursor,
        count: int,
        postagem_url: str,
        collected_at: IsoTimestamp,
    ) -> CommentPage:
        """Busca uma página de comentários de raiz (anonimamente).

        Args:
            photo_id: id do vídeo (``photo_id``/``photoId``).
            cursor: ``pcursor`` da página (vazio na primeira).
            count: itens por página.
            postagem_url: URL da postagem aplicada aos comentários mapeados.
            collected_at: carimbo de coleta aplicado aos comentários.

        Returns:
            A página com as raízes mapeadas e o próximo cursor.

        Raises:
            KwaiTransportError: se todos os gateways falharem no transporte.
            UnexpectedResponseError: se a resposta vier fora do formato esperado.
            KwaiApiError: se o Kwai sinalizar erro de negócio (``result != 1``).
        """
        query, body = self._build_request(photo_id.value, cursor=cursor.value, count=count)
        payload = self._post_to_gateways(path=COMMENT_PATH, query=query, body=body)
        raw_comments = payload.get("rootComments") or []
        comments = [
            RootComment(
                comentario=parse_comment(
                    raw, postagem_url=postagem_url, collected_at=collected_at.value
                ),
                respostas_declaradas=as_int_scalar(raw.get("sub_comment_count")),
            )
            for raw in raw_comments
        ]
        next_cursor = Cursor(str(payload.get("pcursor") or ""))
        return CommentPage(comments=comments, next_cursor=next_cursor)

    def fetch_sub_page(
        self,
        photo_id: PhotoId,
        *,
        root_comment_id: CommentId,
        cursor: Cursor,
        count: int,
        postagem_url: str,
        collected_at: IsoTimestamp,
    ) -> SubCommentPage:
        """Busca uma página de respostas de um comentário raiz (anonimamente).

        Args:
            photo_id: id do vídeo (``photo_id``/``photoId``).
            root_comment_id: id do comentário raiz cujas respostas serão lidas.
            cursor: ``pcursor`` da página (vazio na primeira).
            count: itens por página (o gateway respeita até 100).
            postagem_url: URL da postagem aplicada às respostas mapeadas.
            collected_at: carimbo de coleta aplicado às respostas.

        Returns:
            A página com as respostas mapeadas e o próximo cursor.

        Raises:
            KwaiTransportError: se todos os gateways falharem no transporte.
            UnexpectedResponseError: se a resposta vier fora do formato esperado.
            KwaiApiError: se o Kwai sinalizar erro de negócio (``result != 1``).
        """
        query, body = self._build_sub_request(
            photo_id.value,
            root_comment_id=root_comment_id.value,
            cursor=cursor.value,
            count=count,
        )
        payload = self._post_to_gateways(path=SUBLIST_PATH, query=query, body=body)
        raw_comments = payload.get("subComments") or []
        comments = [
            parse_sub_comment(raw, postagem_url=postagem_url, collected_at=collected_at.value)
            for raw in raw_comments
        ]
        next_cursor = Cursor(str(payload.get("pcursor") or ""))
        return SubCommentPage(comments=comments, next_cursor=next_cursor)

    @staticmethod
    def _signed_query() -> dict[str, str]:
        """Monta a query do app com ``timestamp``/``session_id`` novos."""
        query = dict(DEFAULT_QUERY)
        query["timestamp"] = str(int(time.time() * 1000))
        query["session_id"] = str(uuid.uuid4())
        return query

    @classmethod
    def _build_request(
        cls, photo_id: str, *, cursor: str, count: int
    ) -> tuple[dict[str, str], dict[str, str]]:
        """Monta query e corpo da listagem de raízes, com ``sig`` novo."""
        query = cls._signed_query()
        body = dict(DEFAULT_BODY)
        body["photoId"] = str(photo_id)
        body["count"] = str(count)
        body["pcursor"] = cursor
        body["sig"] = compute_sig({**query, **body})
        return query, body

    @classmethod
    def _build_sub_request(
        cls, photo_id: str, *, root_comment_id: str, cursor: str, count: int
    ) -> tuple[dict[str, str], dict[str, str]]:
        """Monta query e corpo da sublista de respostas, com ``sig`` novo."""
        query = cls._signed_query()
        body = {
            "photoId": str(photo_id),
            "rootCommentId": str(root_comment_id),
            "order": "desc",
            "pcursor": cursor,
            "count": str(max(1, min(count, SUBLIST_MAX_COUNT))),
            "client_key": CLIENT_KEY,
        }
        body["sig"] = compute_sig({**query, **body})
        return query, body

    def _post_to_gateways(
        self, *, path: str, query: dict[str, str], body: dict[str, str]
    ) -> dict[str, Any]:
        """POSTa no primeiro gateway que responder (mesma rota e assinatura).

        Um corpo inválido (HTML de CDN/WAF, por exemplo) conta como falha
        daquele gateway e a escada de fallback segue para o próximo host.

        Raises:
            KwaiTransportError: se todos os gateways falharem.
            KwaiApiError: se o Kwai sinalizar erro de negócio.
        """
        self._rate.wait()
        last_error: Exception | None = None
        for host in COMMENT_HOSTS:
            try:
                response = self._client.post(host + path, params=query, data=body)
                response.raise_for_status()
                payload = decode_json_dict(response)
            except (httpx.HTTPError, UnexpectedResponseError) as exc:
                # Falha transitória do gateway (transporte ou corpo inválido): tenta o próximo.
                last_error = exc
                logger.warning("gateway %s falhou (%s); tentando o próximo", host, exc)
                continue
            ensure_business_success(
                payload,
                default_message="erro de negócio da API móvel do Kwai",
            )
            return payload
        raise KwaiTransportError(f"todos os gateways falharam: {last_error}") from last_error

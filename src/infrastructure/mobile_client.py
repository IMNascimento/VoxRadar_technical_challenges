"""Adapter da API MÓVEL anônima do Kwai (comentários e perfil) — 100% Python.

Descoberta (09/2026, validada contra o app real):
    ``POST /rest/o/comment/list/v2`` (API móvel) aceita uma requisição
    **anônima** (sem login, sem cookies) assinada **apenas com o ``sig``** — a
    fórmula e o preimage estão em :mod:`src.infrastructure.signature`.

    O ``__NS_sig3`` **não** é necessário para estes endpoints (verificado: sem
    ele a resposta é ``result: 1`` com os dados) e, quando presente na
    requisição do app, **não** entra no preimage do ``sig`` — o app o adiciona
    depois da assinatura. A assinatura cobre os parâmetros da *query* **e** do
    corpo.

    As respostas (sub-comentários) vêm de ``POST /rest/o/comment/sublist`` com o
    mesmo contexto e a mesma assinatura; o corpo usa ``rootCommentId`` e exige
    ``client_key`` (sem ele o gateway responde ``result: 40``).

    O feed de um perfil vem de dois passos (2026-10): ``POST /rest/o/user/getInfo``
    resolve ``userIds=@handle`` no id numérico e ``POST /rest/o/feed/profile``
    pagina as postagens por ``pcursor``. **O contexto ideal difere por rota**:
    o ``getInfo`` usa o contexto completo e o feed usa o mínimo validado no coletor.
    O app também retornou feeds com contexto completo; respostas vazias em testes
    anteriores não demonstram uma rejeição universal desse contexto.

Os parâmetros abaixo são o **contexto completo capturado do app** (versão em
:mod:`src.infrastructure.app_identity`): emula o app ao máximo
(``timestamp``/``session_id`` são gerados por requisição, como o app faz). Há
uma **escada de fallback entre gateways**, sem troca automática de contexto.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

import httpx

from ..application.ports import (
    CommentApiPort,
    CommentPage,
    ProfileApiPort,
    ProfilePage,
    RootComment,
    SubCommentPage,
)
from ..config import Settings
from ..domain.business_result import ensure_business_success
from ..domain.value_objects.cursor import Cursor
from ..domain.value_objects.identifiers import CommentId, Handle, PhotoId, UserId
from ..domain.value_objects.iso_timestamp import IsoTimestamp
from ..shared.logging_config import get_logger
from ..shared.utils.coercion import as_int_scalar
from ..shared.utils.ratelimit import RateLimiter
from .app_identity import APP_USER_AGENT, APP_VERSION, CLIENT_KEY
from .exceptions import KwaiTransportError, UnexpectedResponseError
from .http_utils import decode_json_dict, read_cursor, read_object_list, transient_retry
from .mapping import parse_comment, parse_feeds, parse_sub_comment
from .signature import compute_sig

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
# Rotas do perfil (descobertas no app em 2026-10): resolver o handle e paginar.
USER_INFO_PATH = "/rest/o/user/getInfo"
PROFILE_FEED_PATH = "/rest/o/feed/profile"
# Contexto mínimo validado para o feed do coletor, não uma exigência universal da API.
PROFILE_MINIMAL_QUERY: dict[str, str] = {"kpn": "KWAI", "appver": APP_VERSION}

# Contexto/dispositivo do app, capturado do request real (Kwai Lite).
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


class MobileApiAdapter(CommentApiPort, ProfileApiPort):
    """Acesso HTTP à API móvel, implementando as portas de comentários e de perfil."""

    def __init__(self, settings: Settings) -> None:
        """Inicializa a sessão httpx anônima.

        Args:
            settings: configuração do coletor (timeout, delay do rate limit e retries).
        """
        self._max_retries = settings.max_retries
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
        raw_comments = read_object_list(payload, "rootComments", source=COMMENT_PATH)
        comments = [
            RootComment(
                comentario=parse_comment(
                    raw, postagem_url=postagem_url, collected_at=collected_at.value
                ),
                respostas_declaradas=as_int_scalar(raw.get("sub_comment_count")),
            )
            for raw in raw_comments
        ]
        next_cursor = Cursor(read_cursor(payload, source=COMMENT_PATH))
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
        raw_comments = read_object_list(payload, "subComments", source=SUBLIST_PATH)
        comments = [
            parse_sub_comment(raw, postagem_url=postagem_url, collected_at=collected_at.value)
            for raw in raw_comments
        ]
        next_cursor = Cursor(read_cursor(payload, source=SUBLIST_PATH))
        return SubCommentPage(comments=comments, next_cursor=next_cursor)

    def resolve_user(self, handle: Handle) -> UserId:
        """Resolve o handle para o id numérico do usuário (contexto COMPLETO).

        O endpoint exige o ``@`` no ``userIds`` e só devolve o usuário com o
        contexto completo do app — com o mínimo ele responde ``result: 11``.

        Args:
            handle: conta validada, sem ``@``.

        Returns:
            O id numérico do usuário.

        Raises:
            KwaiTransportError: se todos os gateways falharem no transporte.
            UnexpectedResponseError: se o Kwai não devolver o usuário.
            KwaiApiError: se o Kwai sinalizar erro de negócio (``result != 1``).
        """
        query = self._signed_query()
        body = {
            "userIds": f"@{handle.value}",
            "client_key": CLIENT_KEY,
            "os": "android",
        }
        body["sig"] = compute_sig({**query, **body})
        payload = self._post_to_gateways(path=USER_INFO_PATH, query=query, body=body)
        users = read_object_list(payload, "users", source=USER_INFO_PATH)
        primeiro = users[0] if users else None
        if not isinstance(primeiro, dict) or primeiro.get("user_id") is None:
            raise UnexpectedResponseError(f"usuário @{handle.value} não encontrado na resposta")
        return UserId(str(primeiro["user_id"]))

    def fetch_profile_page(
        self,
        user_id: UserId,
        *,
        cursor: Cursor,
        count: int,
        collected_at: IsoTimestamp,
    ) -> ProfilePage:
        """Busca uma página do feed de perfil (contexto MÍNIMO).

        Mantém o contexto mínimo validado no coletor. O app também obteve feeds
        com contexto completo; a diferença entre combinações não foi isolada.

        Args:
            user_id: id numérico resolvido a partir do handle.
            cursor: ``pcursor`` da página (vazio na primeira).
            count: itens por página.
            collected_at: carimbo de coleta aplicado às postagens.

        Returns:
            A página com as postagens mapeadas e o próximo cursor.

        Raises:
            KwaiTransportError: se todos os gateways falharem no transporte.
            KwaiApiError: se o Kwai sinalizar erro de negócio (``result != 1``).
        """
        query = dict(PROFILE_MINIMAL_QUERY)
        body = {
            "user_id": user_id.value,
            "count": str(count),
            "privacy": "public",
            "lang": "en",
            "pcursor": cursor.value,
            "client_key": CLIENT_KEY,
            "os": "android",
        }
        body["sig"] = compute_sig({**query, **body})
        payload = self._post_to_gateways(path=PROFILE_FEED_PATH, query=query, body=body)
        return ProfilePage(
            posts=parse_feeds(payload.get("feeds"), collected_at=collected_at.value),
            next_cursor=Cursor(read_cursor(payload, source=PROFILE_FEED_PATH)),
        )

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
        """POSTa pela escada de gateways, repetindo-a com backoff se todos falharem.

        Só falha de transporte é repetida (``max_retries`` rodadas extras da
        escada); erro de negócio (``result != 1``) sobe na hora.

        Raises:
            KwaiTransportError: se todos os gateways falharem em todas as rodadas.
            KwaiApiError: se o Kwai sinalizar erro de negócio.
        """
        retrying = transient_retry(self._max_retries, on=(KwaiTransportError,))
        return retrying(self._post_through_ladder)(path=path, query=query, body=body)

    def _post_through_ladder(
        self, *, path: str, query: dict[str, str], body: dict[str, str]
    ) -> dict[str, Any]:
        """Uma rodada: POSTa no primeiro gateway que responder (mesma rota e assinatura).

        Um corpo inválido (HTML de CDN/WAF, por exemplo) conta como falha
        daquele gateway e a escada segue para o próximo host.

        Raises:
            KwaiTransportError: se todos os gateways falharem nesta rodada.
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
                source=path,
            )
            return payload
        raise KwaiTransportError(f"todos os gateways falharam: {last_error}") from last_error

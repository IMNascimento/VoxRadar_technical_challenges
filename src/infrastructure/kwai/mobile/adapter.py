"""Adapter da API MÓVEL anônima do Kwai (comentários e perfil) — 100% Python.

Descoberta (09/2026, validada contra o app real):
    ``POST /rest/o/comment/list/v2`` (API móvel) aceita uma requisição
    **anônima** (sem login, sem cookies) assinada **apenas com o ``sig``** — a
    fórmula e o preimage estão em :mod:`src.infrastructure.kwai.mobile.signature`.

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
:mod:`src.infrastructure.kwai.mobile.app_identity`): emula o app ao máximo
(``timestamp``/``session_id`` são gerados por requisição, como o app faz). A
sessão, a assinatura e a escada de gateways ficam no :class:`MobileApiClient`;
aqui fica o que é de cada rota: caminho, contexto, corpo e tamanho de página.
"""

from __future__ import annotations

import time
import uuid

from ....application.dtos.pages import CommentPage, ProfilePage, RootComment, SubCommentPage
from ....application.ports.comment_api_port import ICommentApiPort
from ....application.ports.profile_api_port import IProfileApiPort
from ....domain.value_objects.cursor import Cursor
from ....domain.value_objects.identifiers import CommentId, Handle, UserId
from ....domain.value_objects.iso_timestamp import IsoTimestamp
from ....domain.value_objects.post_reference import PostReference
from ..coercion import as_int_scalar
from ..exceptions import UnexpectedResponseError
from ..http_utils import read_cursor, read_object_list
from ..mapping import parse_comment, parse_feeds, parse_sub_comment
from .app_identity import APP_VERSION, CLIENT_KEY
from .client import MobileApiClient

COMMENT_PATH = "/rest/o/comment/list/v2"
SUBLIST_PATH = "/rest/o/comment/sublist"
# Itens por página de raízes (sem ``count`` o gateway devolve 5; 20, 50 e 100 são respeitados).
COMMENTS_PAGE_SIZE = 50
# Itens por página da sublista de respostas (o gateway respeita até 100).
SUBLIST_PAGE_SIZE = 100
# Itens por página do feed de perfil (o app pede 30; 30 é respeitado).
PROFILE_PAGE_SIZE = 30
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

# Corpo enviado pelo app; ``count`` é o tamanho de página de cada rota.
DEFAULT_BODY: dict[str, str] = {
    "order": "desc",
    "photoPageType": "0",
    "requestType": "3",
    "isPreload": "false",
    "preloadSource": "",
    "os": "android",
    "client_key": CLIENT_KEY,
}


class MobileApiAdapter(ICommentApiPort, IProfileApiPort):
    """Rotas da API móvel, implementando as portas de comentários e de perfil."""

    def __init__(self, client: MobileApiClient) -> None:
        """Inicializa o adapter.

        Args:
            client: cliente da API móvel, dono da sessão HTTP e da assinatura.
        """
        self._client = client

    def fetch_page(
        self,
        post: PostReference,
        *,
        cursor: Cursor,
        collected_at: IsoTimestamp,
    ) -> CommentPage:
        """Busca uma página de comentários de raiz (anonimamente).

        Args:
            post: postagem alvo; o id vai em ``photoId`` e a URL nos comentários mapeados.
            cursor: ``pcursor`` da página (vazio na primeira).
            collected_at: carimbo de coleta aplicado aos comentários.

        Returns:
            A página com as raízes mapeadas e o próximo cursor.

        Raises:
            KwaiTransportError: se todos os gateways falharem no transporte.
            UnexpectedResponseError: se a resposta vier fora do formato esperado.
            KwaiApiError: se o Kwai sinalizar erro de negócio (``result != 1``).
        """
        body = {
            **DEFAULT_BODY,
            "photoId": post.photo_id.value,
            "count": str(COMMENTS_PAGE_SIZE),
            "pcursor": cursor.value,
        }
        payload = self._client.post(COMMENT_PATH, query=_app_query(), body=body)
        raw_comments = read_object_list(payload, "rootComments", source=COMMENT_PATH)
        comments = [
            RootComment(
                comment=parse_comment(raw, post_url=post.url, collected_at=collected_at.value),
                declared_replies=as_int_scalar(raw.get("sub_comment_count")),
            )
            for raw in raw_comments
        ]
        next_cursor = Cursor(read_cursor(payload, source=COMMENT_PATH))
        return CommentPage(comments=comments, next_cursor=next_cursor)

    def fetch_sub_page(
        self,
        post: PostReference,
        *,
        root_comment_id: CommentId,
        cursor: Cursor,
        collected_at: IsoTimestamp,
    ) -> SubCommentPage:
        """Busca uma página de respostas de um comentário raiz (anonimamente).

        Args:
            post: postagem alvo; o id vai em ``photoId`` e a URL nas respostas mapeadas.
            root_comment_id: id do comentário raiz cujas respostas serão lidas.
            cursor: ``pcursor`` da página (vazio na primeira).
            collected_at: carimbo de coleta aplicado às respostas.

        Returns:
            A página com as respostas mapeadas e o próximo cursor.

        Raises:
            KwaiTransportError: se todos os gateways falharem no transporte.
            UnexpectedResponseError: se a resposta vier fora do formato esperado.
            KwaiApiError: se o Kwai sinalizar erro de negócio (``result != 1``).
        """
        body = {
            "photoId": post.photo_id.value,
            "rootCommentId": root_comment_id.value,
            "order": "desc",
            "pcursor": cursor.value,
            "count": str(SUBLIST_PAGE_SIZE),
            "client_key": CLIENT_KEY,
        }
        payload = self._client.post(SUBLIST_PATH, query=_app_query(), body=body)
        raw_comments = read_object_list(payload, "subComments", source=SUBLIST_PATH)
        comments = [
            parse_sub_comment(raw, post_url=post.url, collected_at=collected_at.value)
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
        body = {"userIds": f"@{handle.value}", "client_key": CLIENT_KEY, "os": "android"}
        payload = self._client.post(USER_INFO_PATH, query=_app_query(), body=body)
        users = read_object_list(payload, "users", source=USER_INFO_PATH)
        first_user = users[0] if users else None
        if first_user is None or first_user.get("user_id") is None:
            raise UnexpectedResponseError(f"usuário @{handle.value} não encontrado na resposta")
        return UserId(str(first_user["user_id"]))

    def fetch_profile_page(
        self,
        user_id: UserId,
        *,
        cursor: Cursor,
        collected_at: IsoTimestamp,
    ) -> ProfilePage:
        """Busca uma página do feed de perfil (contexto MÍNIMO).

        Mantém o contexto mínimo validado no coletor. O app também obteve feeds
        com contexto completo; a diferença entre combinações não foi isolada.

        Args:
            user_id: id numérico resolvido a partir do handle.
            cursor: ``pcursor`` da página (vazio na primeira).
            collected_at: carimbo de coleta aplicado às postagens.

        Returns:
            A página com as postagens mapeadas e o próximo cursor.

        Raises:
            KwaiTransportError: se todos os gateways falharem no transporte.
            KwaiApiError: se o Kwai sinalizar erro de negócio (``result != 1``).
        """
        body = {
            "user_id": user_id.value,
            "count": str(PROFILE_PAGE_SIZE),
            "privacy": "public",
            "lang": "en",
            "pcursor": cursor.value,
            "client_key": CLIENT_KEY,
            "os": "android",
        }
        query = dict(PROFILE_MINIMAL_QUERY)
        payload = self._client.post(PROFILE_FEED_PATH, query=query, body=body)
        return ProfilePage(
            posts=parse_feeds(payload.get("feeds"), collected_at=collected_at.value),
            next_cursor=Cursor(read_cursor(payload, source=PROFILE_FEED_PATH)),
        )


def _app_query() -> dict[str, str]:
    """Monta a query completa do app com ``timestamp``/``session_id`` novos."""
    query = dict(DEFAULT_QUERY)
    query["timestamp"] = str(int(time.time() * 1000))
    query["session_id"] = str(uuid.uuid4())
    return query

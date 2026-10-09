"""Testes do assinador/API móvel (sem rede)."""

from __future__ import annotations

import urllib.parse
from typing import Any

import httpx
import pytest
import respx

from src.config.settings import Settings
from src.domain.value_objects.cursor import Cursor
from src.domain.value_objects.identifiers import CommentId, Handle, PhotoId, UserId
from src.domain.value_objects.iso_timestamp import IsoTimestamp
from src.domain.value_objects.post_reference import PostReference
from src.infrastructure.kwai.exceptions import (
    KwaiApiError,
    KwaiTransportError,
    UnexpectedResponseError,
)
from src.infrastructure.kwai.mobile.adapter import (
    COMMENT_PATH,
    DEFAULT_BODY,
    DEFAULT_QUERY,
    PROFILE_FEED_PATH,
    PROFILE_MINIMAL_QUERY,
    SUBLIST_PAGE_SIZE,
    SUBLIST_PATH,
    USER_INFO_PATH,
    MobileApiAdapter,
)
from src.infrastructure.kwai.mobile.app_identity import APP_VERSION, CLIENT_KEY
from src.infrastructure.kwai.mobile.client import (
    COMMENT_FALLBACK_HOSTS,
    COMMENT_HOST,
    MobileApiClient,
)
from src.infrastructure.kwai.mobile.signature import compute_sig

# Vetor REAL capturado de um request do Kwai Lite (comment/list/v2).
_QUERY = {
    "mod": "Google(sdk_gphone_x86)",
    "appver": "10.3.20.539600",
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
    "timestamp": "1789426280954",
    "session_id": "c9deb0a8-a93c-4c6a-9b69-aa7be5913288",
    "did": "ANDROID_c3d0873a15becaef",
}
_BODY = {
    "photoId": "5246843676744520217",
    "user_id": "150001367557373",
    "order": "desc",
    "count": "10",
    "photoPageType": "0",
    "requestType": "3",
    "llsid": "4887332167313625699",
    "isPreload": "false",
    "preloadSource": "",
    "os": "android",
    "client_key": "3c2cd3f3",
    "adExtInfo": (
        r'{"gaid":"017345d0-c209-4da0-a76d-cff87c0c241c","userAgent":'
        r'"Dalvik\/2.1.0 (Linux; U; Android 11; sdk_gphone_x86 Build\/RSR1.240422.006)"}'
    ),
}
_APP_SIG = "a1f8385e9b1e3ac7006c4b9d84be2014"

# O request real do app (hook OkHttp) também trazia `__NS_sig3` na query, que
# NÃO entra no preimage do `sig`. O algoritmo de `sig3` não foi reproduzido;
# as entradas observadas de `atlasSign` não eram apenas caminho + `sig`.
_APP_SIG3 = "hMzS5wHHExtlOGY5YmRhYWM2YjI2Y2VhYmJhMGEzYTI2MjBjZDFiYWQxYzIxM2QwYmViMWJmYTk"


def test_compute_sig_reproduz_o_sig_do_app() -> None:
    assert compute_sig({**_QUERY, **_BODY}) == _APP_SIG


def test_versao_do_app_e_o_vetor_do_sal_andam_juntos() -> None:
    """O sal só é provado para a versão do app do vetor real acima.

    Trocar ``APP_VERSION`` sem capturar um vetor novo (e revalidar o sal) quebra
    a assinatura (``result: 50``); este teste força atualizar os dois juntos.
    """
    assert _QUERY["appver"] == APP_VERSION
    assert PROFILE_MINIMAL_QUERY["appver"] == APP_VERSION
    assert DEFAULT_QUERY["appver"] == APP_VERSION


def test_compute_sig_ignora_tokens_derivados() -> None:
    params = {**_QUERY, "__NS_sig3": _APP_SIG3, **_BODY}
    assert compute_sig(params) == _APP_SIG


def test_compute_sig_ordena_chaves_e_muda_com_parametro() -> None:
    assert compute_sig({"b": "2", "a": "1"}) == compute_sig({"a": "1", "b": "2"})
    assert compute_sig({"a": "1"}) != compute_sig({"a": "2"})


@respx.mock
def test_requisicao_envia_o_contexto_completo_do_app(settings: Settings) -> None:
    """Trava o contrato do contexto completo do app.

    Se alguém reduzir `DEFAULT_QUERY`/`DEFAULT_BODY` "por limpeza", este teste
    falha: esse contexto é intencional. O fallback troca gateways, não parâmetros.
    """
    route = respx.post(COMMENT_HOST + COMMENT_PATH).mock(
        return_value=httpx.Response(
            200, json={"result": 1, "pcursor": "no_more", "rootComments": []}
        )
    )
    client = MobileApiClient(settings)
    adapter = MobileApiAdapter(client)
    try:
        adapter.fetch_page(
            PostReference(
                PhotoId("5246843676744520217"),
                "https://www.kwai.com/@perfil/video/5246843676744520217",
            ),
            cursor=Cursor(""),
            collected_at=IsoTimestamp("2026-09-08T00:00:00Z"),
        )
    finally:
        client.close()

    request = route.calls.last.request
    sent_query = dict(urllib.parse.parse_qsl(request.url.query.decode(), keep_blank_values=True))
    sent_body: dict[str, Any] = dict(
        urllib.parse.parse_qsl(request.content.decode(), keep_blank_values=True)
    )

    assert set(sent_query) == set(DEFAULT_QUERY) | {"timestamp", "session_id"}
    assert set(sent_body) == set(DEFAULT_BODY) | {"photoId", "count", "pcursor", "sig"}
    assert len(sent_query) == len(DEFAULT_QUERY) + 2
    assert sent_body["count"] == "50"
    # o `sig` cobre query + corpo (sem ele mesmo)
    assert sent_body["sig"] == compute_sig(
        {**sent_query, **{k: v for k, v in sent_body.items() if k != "sig"}}
    )


@respx.mock
def test_erro_de_negocio_nao_troca_de_gateway(settings: Settings) -> None:
    """`result != 1` é erro de negócio: falha no 1º host SEM tentar o fallback."""
    primeira = respx.post(COMMENT_HOST + COMMENT_PATH).mock(
        return_value=httpx.Response(200, json={"result": 2})
    )
    fallbacks = [
        respx.post(host + COMMENT_PATH).mock(
            return_value=httpx.Response(
                200, json={"result": 1, "pcursor": "no_more", "rootComments": []}
            )
        )
        for host in COMMENT_FALLBACK_HOSTS
    ]
    client = MobileApiClient(settings)
    adapter = MobileApiAdapter(client)
    try:
        with pytest.raises(KwaiApiError) as exc:
            adapter.fetch_page(
                PostReference(
                    PhotoId("5246843676744520217"),
                    "https://www.kwai.com/@perfil/video/5246843676744520217",
                ),
                cursor=Cursor(""),
                collected_at=IsoTimestamp("2026-09-08T00:00:00Z"),
            )
    finally:
        client.close()

    assert len(primeira.calls) == 1
    assert all(len(route.calls) == 0 for route in fallbacks)
    assert exc.value.result == 2
    assert str(exc.value) == f"erro de negócio da API móvel do Kwai (result=2) em {COMMENT_PATH}"


@respx.mock
def test_falha_de_rede_no_primeiro_host_tenta_o_proximo(settings: Settings) -> None:
    """Falha transitória (rede) no 1º host DEVE escalar o fallback até o sucesso."""
    primeira = respx.post(COMMENT_HOST + COMMENT_PATH).mock(
        side_effect=httpx.ConnectError("gateway fora do ar")
    )
    segunda = respx.post(COMMENT_FALLBACK_HOSTS[0] + COMMENT_PATH).mock(
        return_value=httpx.Response(
            200, json={"result": 1, "pcursor": "no_more", "rootComments": []}
        )
    )
    client = MobileApiClient(settings)
    adapter = MobileApiAdapter(client)
    try:
        page = adapter.fetch_page(
            PostReference(
                PhotoId("5246843676744520217"),
                "https://www.kwai.com/@perfil/video/5246843676744520217",
            ),
            cursor=Cursor(""),
            collected_at=IsoTimestamp("2026-09-08T00:00:00Z"),
        )
    finally:
        client.close()

    assert len(primeira.calls) == 1
    assert len(segunda.calls) == 1
    assert page.comments == []
    assert page.next_cursor.value == ""


@respx.mock
def test_resposta_sem_root_comments_vira_pagina_vazia(settings: Settings) -> None:
    """`rootComments` ausente é tolerado: página vazia em vez de erro."""
    respx.post(COMMENT_HOST + COMMENT_PATH).mock(
        return_value=httpx.Response(200, json={"result": 1, "pcursor": "no_more"})
    )
    client = MobileApiClient(settings)
    adapter = MobileApiAdapter(client)
    try:
        page = adapter.fetch_page(
            PostReference(
                PhotoId("5246843676744520217"),
                "https://www.kwai.com/@perfil/video/5246843676744520217",
            ),
            cursor=Cursor(""),
            collected_at=IsoTimestamp("2026-09-08T00:00:00Z"),
        )
    finally:
        client.close()

    assert page.comments == []
    assert page.next_cursor.value == ""


@respx.mock
def test_corpo_nao_json_no_host_primario_cai_para_o_fallback(settings: Settings) -> None:
    """Corpo não-JSON (HTML de CDN/WAF) conta como falha do gateway: fallback assume."""
    primario = respx.post(COMMENT_HOST + COMMENT_PATH).mock(
        return_value=httpx.Response(200, text="<html>challenge</html>")
    )
    fallback = respx.post(COMMENT_FALLBACK_HOSTS[0] + COMMENT_PATH).mock(
        return_value=httpx.Response(
            200, json={"result": 1, "pcursor": "no_more", "rootComments": []}
        )
    )
    client = MobileApiClient(settings)
    adapter = MobileApiAdapter(client)
    try:
        page = adapter.fetch_page(
            PostReference(
                PhotoId("5246843676744520217"),
                "https://www.kwai.com/@perfil/video/5246843676744520217",
            ),
            cursor=Cursor(""),
            collected_at=IsoTimestamp("2026-09-08T00:00:00Z"),
        )
    finally:
        client.close()

    assert len(primario.calls) == 1
    assert len(fallback.calls) == 1
    assert page.next_cursor.value == ""


@respx.mock
def test_corpo_nao_json_em_todos_os_hosts_levanta_erro_de_transporte(settings: Settings) -> None:
    """Esgotada a escada de hosts com 200 não-JSON, falha com causa UnexpectedResponseError."""
    rotas = [
        respx.post(host + COMMENT_PATH).mock(
            return_value=httpx.Response(200, text="<html>challenge</html>")
        )
        for host in (COMMENT_HOST, *COMMENT_FALLBACK_HOSTS)
    ]
    client = MobileApiClient(settings)
    adapter = MobileApiAdapter(client)
    try:
        with pytest.raises(KwaiTransportError) as exc:
            adapter.fetch_page(
                PostReference(
                    PhotoId("5246843676744520217"),
                    "https://www.kwai.com/@perfil/video/5246843676744520217",
                ),
                cursor=Cursor(""),
                collected_at=IsoTimestamp("2026-09-08T00:00:00Z"),
            )
    finally:
        client.close()

    assert all(len(route.calls) == 1 for route in rotas)
    assert isinstance(exc.value.__cause__, UnexpectedResponseError)


@respx.mock
def test_fetch_sub_page_vai_para_sublist_e_mapeia_vinculo(settings: Settings) -> None:
    """A sublista usa ``/rest/o/comment/sublist`` com ``rootCommentId`` e ``client_key``."""
    route = respx.post(COMMENT_HOST + SUBLIST_PATH).mock(
        return_value=httpx.Response(
            200,
            json={
                "result": 1,
                "pcursor": "no_more",
                "subComments": [
                    {
                        "comment_id": "s_1",
                        "content": "resposta",
                        "author_name": "Quem responde",
                        "author_id": "a2",
                        "liked_count": 3,
                        "reply_to": 150001404765512,
                        "replyToUserName": "Fulano",
                        "timestamp": 1700000000000,
                    }
                ],
            },
        )
    )
    client = MobileApiClient(settings)
    adapter = MobileApiAdapter(client)
    try:
        page = adapter.fetch_sub_page(
            PostReference(
                PhotoId("5246843676744520217"),
                "https://www.kwai.com/@perfil/video/5246843676744520217",
            ),
            root_comment_id=CommentId("155133451079517322"),
            cursor=Cursor(""),
            collected_at=IsoTimestamp("2026-09-08T00:00:00Z"),
        )
    finally:
        client.close()

    sent_body = dict(
        urllib.parse.parse_qsl(route.calls.last.request.content.decode(), keep_blank_values=True)
    )
    assert sent_body["rootCommentId"] == "155133451079517322"
    assert sent_body["client_key"] == CLIENT_KEY
    assert sent_body["photoId"] == "5246843676744520217"
    assert "sig" in sent_body
    assert page.next_cursor.value == ""
    assert [sub.comment.id for sub in page.comments] == ["s_1"]
    assert page.comments[0].reply_to_id == "150001404765512"
    assert page.comments[0].reply_to_usuario == "Fulano"


@respx.mock
def test_fetch_sub_page_pede_o_tamanho_de_pagina_da_sublista(settings: Settings) -> None:
    route = respx.post(COMMENT_HOST + SUBLIST_PATH).mock(
        return_value=httpx.Response(
            200, json={"result": 1, "pcursor": "no_more", "subComments": []}
        )
    )
    client = MobileApiClient(settings)
    adapter = MobileApiAdapter(client)
    try:
        adapter.fetch_sub_page(
            PostReference(PhotoId("1"), "https://www.kwai.com/@p/video/1"),
            root_comment_id=CommentId("9"),
            cursor=Cursor(""),
            collected_at=IsoTimestamp("2026-09-08T00:00:00Z"),
        )
        sent = dict(
            urllib.parse.parse_qsl(
                route.calls.last.request.content.decode(), keep_blank_values=True
            )
        )
        assert sent["count"] == str(SUBLIST_PAGE_SIZE)
    finally:
        client.close()


@respx.mock
def test_sublist_erro_de_negocio_nao_troca_gateway(settings: Settings) -> None:
    primeira = respx.post(COMMENT_HOST + SUBLIST_PATH).mock(
        return_value=httpx.Response(200, json={"result": 40, "error_msg": "busy"})
    )
    fallbacks = [
        respx.post(host + SUBLIST_PATH).mock(
            return_value=httpx.Response(
                200, json={"result": 1, "pcursor": "no_more", "subComments": []}
            )
        )
        for host in COMMENT_FALLBACK_HOSTS
    ]
    client = MobileApiClient(settings)
    adapter = MobileApiAdapter(client)
    try:
        with pytest.raises(KwaiApiError) as exc:
            adapter.fetch_sub_page(
                PostReference(PhotoId("1"), "https://www.kwai.com/@p/video/1"),
                root_comment_id=CommentId("9"),
                cursor=Cursor(""),
                collected_at=IsoTimestamp("2026-09-08T00:00:00Z"),
            )
    finally:
        client.close()

    assert len(primeira.calls) == 1
    assert all(len(route.calls) == 0 for route in fallbacks)
    assert exc.value.result == 40


@respx.mock
def test_sublist_corpo_invalido_no_primario_cai_para_o_fallback(settings: Settings) -> None:
    primario = respx.post(COMMENT_HOST + SUBLIST_PATH).mock(
        return_value=httpx.Response(200, text="<html>challenge</html>")
    )
    fallback = respx.post(COMMENT_FALLBACK_HOSTS[0] + SUBLIST_PATH).mock(
        return_value=httpx.Response(
            200, json={"result": 1, "pcursor": "no_more", "subComments": []}
        )
    )
    client = MobileApiClient(settings)
    adapter = MobileApiAdapter(client)
    try:
        page = adapter.fetch_sub_page(
            PostReference(PhotoId("1"), "https://www.kwai.com/@p/video/1"),
            root_comment_id=CommentId("9"),
            cursor=Cursor(""),
            collected_at=IsoTimestamp("2026-09-08T00:00:00Z"),
        )
    finally:
        client.close()

    assert len(primario.calls) == 1
    assert len(fallback.calls) == 1
    assert page.next_cursor.value == ""


@respx.mock
def test_get_info_envia_contexto_completo_e_arroba(settings: Settings) -> None:
    """Trava o contrato do ``getInfo``: contexto COMPLETO e ``userIds`` com ``@``.

    Com o contexto mínimo este endpoint responde ``result: 11`` e sem o ``@``
    devolve ``users: []`` — por isso os dois detalhes ficam travados aqui.
    """
    route = respx.post(COMMENT_HOST + USER_INFO_PATH).mock(
        return_value=httpx.Response(
            200,
            json={"result": 1, "users": [{"user_id": 150001214685137, "user_name": "Perfil"}]},
        )
    )
    client = MobileApiClient(settings)
    adapter = MobileApiAdapter(client)
    try:
        resolved = adapter.resolve_user(Handle("parkourcity"))
    finally:
        client.close()

    request = route.calls.last.request
    sent_query = dict(urllib.parse.parse_qsl(request.url.query.decode(), keep_blank_values=True))
    sent_body: dict[str, Any] = dict(
        urllib.parse.parse_qsl(request.content.decode(), keep_blank_values=True)
    )

    assert set(sent_query) == set(DEFAULT_QUERY) | {"timestamp", "session_id"}
    assert set(sent_body) == {"userIds", "client_key", "os", "sig"}
    assert sent_body["userIds"] == "@parkourcity"
    assert resolved == UserId("150001214685137")


@respx.mock
def test_feed_de_perfil_usa_o_contexto_minimo(settings: Settings) -> None:
    """Preserva o contexto mínimo validado no coletor, sem exigir isso da API."""
    route = respx.post(COMMENT_HOST + PROFILE_FEED_PATH).mock(
        return_value=httpx.Response(200, json={"result": 1, "pcursor": "c1", "feeds": []})
    )
    client = MobileApiClient(settings)
    adapter = MobileApiAdapter(client)
    try:
        page = adapter.fetch_profile_page(
            UserId("150001214685137"),
            cursor=Cursor(""),
            collected_at=IsoTimestamp("2026-09-08T00:00:00Z"),
        )
    finally:
        client.close()

    request = route.calls.last.request
    sent_query = dict(urllib.parse.parse_qsl(request.url.query.decode(), keep_blank_values=True))
    sent_body: dict[str, Any] = dict(
        urllib.parse.parse_qsl(request.content.decode(), keep_blank_values=True)
    )

    assert sent_query == PROFILE_MINIMAL_QUERY
    assert set(sent_body) == {
        "user_id",
        "count",
        "privacy",
        "lang",
        "pcursor",
        "client_key",
        "os",
        "sig",
    }
    assert sent_body["user_id"] == "150001214685137"
    assert sent_body["count"] == "30"
    assert page.next_cursor.value == "c1"
    assert page.posts == []


@respx.mock
def test_get_info_sem_usuario_levanta_erro(settings: Settings) -> None:
    """Resposta válida mas sem usuário não pode virar coleta silenciosa vazia."""
    respx.post(COMMENT_HOST + USER_INFO_PATH).mock(
        return_value=httpx.Response(200, json={"result": 1, "users": []})
    )
    client = MobileApiClient(settings)
    adapter = MobileApiAdapter(client)
    try:
        with pytest.raises(UnexpectedResponseError):
            adapter.resolve_user(Handle("nao_existe"))
    finally:
        client.close()


# --- retry da escada de gateways --------------------------------------------

_PAGINA_VAZIA = {"result": 1, "pcursor": "no_more", "rootComments": []}


def _buscar_primeira_pagina(adapter: MobileApiAdapter) -> Any:
    return adapter.fetch_page(
        PostReference(
            PhotoId("5246843676744520217"), "https://www.kwai.com/@perfil/video/5246843676744520217"
        ),
        cursor=Cursor(""),
        collected_at=IsoTimestamp("2026-09-08T00:00:00Z"),
    )


@pytest.mark.parametrize(
    "falha",
    [httpx.ConnectError("gateway fora do ar"), httpx.Response(429), httpx.Response(503)],
    ids=["rede", "429", "503"],
)
@respx.mock
def test_escada_inteira_falhando_e_repetida_com_backoff(
    retry_settings: Settings, no_backoff: list[float], falha: Any
) -> None:
    """Todos os gateways caem na 1ª rodada: a escada recomeça depois do backoff."""
    primario = respx.post(COMMENT_HOST + COMMENT_PATH).mock(
        side_effect=[falha, httpx.Response(200, json=_PAGINA_VAZIA)]
    )
    fallbacks = [
        respx.post(host + COMMENT_PATH).mock(side_effect=[falha]) for host in COMMENT_FALLBACK_HOSTS
    ]
    client = MobileApiClient(retry_settings)
    adapter = MobileApiAdapter(client)
    try:
        page = _buscar_primeira_pagina(adapter)
    finally:
        client.close()

    assert len(primario.calls) == 2
    assert all(len(route.calls) == 1 for route in fallbacks)
    assert len(no_backoff) == 1
    assert page.next_cursor.value == ""


@respx.mock
def test_resolucao_do_handle_tambem_repete_a_escada(
    retry_settings: Settings, no_backoff: list[float]
) -> None:
    """O ``getInfo`` passa pela mesma escada: uma rodada inteira caída é repetida."""
    info_ok = {"result": 1, "users": [{"user_id": 150001214685137}]}
    primario = respx.post(COMMENT_HOST + USER_INFO_PATH).mock(
        side_effect=[httpx.ConnectError("fora do ar"), httpx.Response(200, json=info_ok)]
    )
    for host in COMMENT_FALLBACK_HOSTS:
        respx.post(host + USER_INFO_PATH).mock(side_effect=[httpx.ConnectError("fora do ar")])
    client = MobileApiClient(retry_settings)
    adapter = MobileApiAdapter(client)
    try:
        resolved = adapter.resolve_user(Handle("parkourcity"))
    finally:
        client.close()

    assert resolved == UserId("150001214685137")
    assert len(primario.calls) == 2
    assert len(no_backoff) == 1


@respx.mock
def test_falha_permanente_esgota_os_retries_e_levanta_erro_de_transporte(
    retry_settings: Settings, no_backoff: list[float]
) -> None:
    """Com ``max_retries=2`` são 3 rodadas da escada e depois o erro de transporte."""
    rotas = [
        respx.post(host + COMMENT_PATH).mock(side_effect=httpx.ConnectError("fora do ar"))
        for host in (COMMENT_HOST, *COMMENT_FALLBACK_HOSTS)
    ]
    client = MobileApiClient(retry_settings)
    adapter = MobileApiAdapter(client)
    try:
        with pytest.raises(KwaiTransportError):
            _buscar_primeira_pagina(adapter)
    finally:
        client.close()

    assert all(len(route.calls) == 3 for route in rotas)
    assert len(no_backoff) == 2


@respx.mock
def test_erro_de_negocio_nao_e_repetido_mesmo_com_retries(
    retry_settings: Settings, no_backoff: list[float]
) -> None:
    rota = respx.post(COMMENT_HOST + COMMENT_PATH).mock(
        return_value=httpx.Response(200, json={"result": 50, "error_msg": "assinatura"})
    )
    client = MobileApiClient(retry_settings)
    adapter = MobileApiAdapter(client)
    try:
        with pytest.raises(KwaiApiError):
            _buscar_primeira_pagina(adapter)
    finally:
        client.close()

    assert len(rota.calls) == 1
    assert no_backoff == []

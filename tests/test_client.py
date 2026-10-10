import httpx
import pytest
import respx

from kwai_collector import client

# request real do app (comment/list/v2) com o sig que ele mandou
QUERY = {
    **client.APP_QUERY,
    "timestamp": "1789426280954",
    "session_id": "c9deb0a8-a93c-4c6a-9b69-aa7be5913288",
}
BODY = {
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


def test_sig_igual_ao_do_app():
    assert client.create_signature({**QUERY, **BODY}) == "a1f8385e9b1e3ac7006c4b9d84be2014"


def test_sig_ignora_tokens_extras():
    assert client.create_signature(
        {**QUERY, **BODY, "__NS_sig3": "abc"}
    ) == client.create_signature({**QUERY, **BODY})


@respx.mock
def test_tenta_o_proximo_host_quando_um_falha():
    path = "/rest/o/comment/list/v2"
    respx.post(client.MOBILE_HOSTS[0] + path).mock(return_value=httpx.Response(503))
    second = respx.post(client.MOBILE_HOSTS[1] + path).mock(
        return_value=httpx.Response(200, json={"result": 1, "rootComments": []})
    )

    data = client.post_mobile(path, {"a": "1"}, {"b": "2"})

    assert data["result"] == 1
    assert second.called
    assert "sig=" in second.calls[0].request.content.decode()


@respx.mock
def test_erro_de_negocio_nao_tenta_de_novo():
    route = respx.post(client.WEB_URL + "/x").mock(
        return_value=httpx.Response(200, json={"result": 2, "error_msg": "bloqueado"})
    )
    with pytest.raises(client.KwaiError, match="bloqueado"):
        client.post_web("/x", {})
    assert route.call_count == 1


@respx.mock
def test_desiste_depois_dos_retries():
    route = respx.post(client.WEB_URL + "/x").mock(return_value=httpx.Response(500))
    with pytest.raises(client.KwaiError):
        client.post_web("/x", {})
    assert route.call_count == 2  # 1 tentativa + 1 retry (MAX_RETRIES=1 no conftest)


@respx.mock
def test_erro_4xx_nao_tenta_de_novo():
    route = respx.post(client.WEB_URL + "/x").mock(return_value=httpx.Response(403))
    with pytest.raises(client.KwaiError):
        client.post_web("/x", {})
    assert route.call_count == 1

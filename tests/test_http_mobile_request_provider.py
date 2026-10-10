import httpx

from kwai_collector.security.http_mobile_request_provider import (
    HttpMobileRequestProvider,
)


def test_http_provider_prepara_request():
    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        assert request.method == "POST"
        assert str(request.url) == ("http://auth.local/prepare")

        payload = request.read().decode("utf-8")

        assert '"query"' in payload
        assert '"body"' in payload
        assert '"headers"' in payload

        return httpx.Response(
            200,
            json={
                "query": {
                    "llsid": "123",
                    "extra": "q",
                },
                "body": {
                    "photoId": "999",
                    "test_sig": "fake",
                },
                "headers": {
                    "Accept": "application/json",
                    "X-Test": "1",
                },
            },
        )

    transport = httpx.MockTransport(handler)

    client = httpx.Client(transport=transport)

    provider = HttpMobileRequestProvider(
        endpoint="http://auth.local/prepare",
        client=client,
    )

    resultado = provider.prepare(
        query={
            "llsid": "123",
        },
        body={
            "photoId": "999",
        },
        headers={
            "Accept": "application/json",
        },
    )

    assert resultado.query == {
        "llsid": "123",
        "extra": "q",
    }

    assert resultado.body == {
        "photoId": "999",
        "test_sig": "fake",
    }

    assert resultado.headers == {
        "Accept": "application/json",
        "X-Test": "1",
    }


def test_http_provider_envia_token_bearer():
    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        assert request.headers.get("Authorization") == "Bearer teste-token"

        return httpx.Response(
            200,
            json={
                "query": {},
                "body": {},
                "headers": {},
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))

    provider = HttpMobileRequestProvider(
        endpoint="http://auth.local/prepare",
        token="teste-token",
        client=client,
    )

    provider.prepare(
        query={},
        body={},
        headers={},
    )


def test_http_provider_rejeita_resposta_invalida():
    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        del request

        return httpx.Response(
            200,
            json={
                "query": {},
                "body": "invalido",
                "headers": {},
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))

    provider = HttpMobileRequestProvider(
        endpoint="http://auth.local/prepare",
        client=client,
    )

    try:
        provider.prepare(
            query={},
            body={},
            headers={},
        )

    except TypeError as exc:
        assert "body" in str(exc)

    else:
        raise AssertionError("Era esperado TypeError.")

from __future__ import annotations

from urllib.parse import parse_qs

import httpx
import pytest

from kwai_collector.clients.live_comment_client import (
    LiveCommentClient,
    extract_ids_from_url,
)
from kwai_collector.security.signature_provider import (
    PreparedMobileRequest,
)


class RecordingAuthProvider:
    """
    Provider usado apenas no teste.

    Ele não gera autenticação nem assinatura.
    Apenas registra cada request recebida e
    devolve query/body/headers sem alterações.
    """

    def __init__(self) -> None:
        self.calls: list[dict[str, dict[str, str]]] = []

    def prepare(
        self,
        *,
        query: dict[str, str],
        body: dict[str, str],
        headers: dict[str, str],
    ) -> PreparedMobileRequest:
        self.calls.append(
            {
                "query": dict(query),
                "body": dict(body),
                "headers": dict(headers),
            }
        )

        return PreparedMobileRequest(
            query=dict(query),
            body=dict(body),
            headers=dict(headers),
        )


def _make_comments(
    start: int,
    amount: int,
) -> list[dict[str, str]]:
    """
    Cria comentários falsos para simular
    as respostas paginadas do endpoint.
    """
    comments: list[dict[str, str]] = []

    for number in range(
        start,
        start + amount,
    ):
        identifier = f"comment-{number}"

        comments.append(
            {
                "id": identifier,
                "commentId": identifier,
                "comment_id": identifier,
                "content": f"Comentário {number}",
            }
        )

    return comments


def test_live_comment_client_paginate_20_20_10() -> None:
    """
    Simula:

        página 1 -> 20 comentários
        página 2 -> 20 comentários
        página 3 -> 10 comentários

    Total esperado:

        50 comentários

    Também valida que o auth provider é
    chamado novamente para cada pcursor.
    """

    auth_provider = RecordingAuthProvider()

    received_requests: list[dict[str, str]] = []

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        """
        Handler usado pelo MockTransport.

        Nenhuma chamada real é enviada para
        a API do Kwai.
        """

        body_raw = request.content.decode("utf-8")

        parsed = parse_qs(
            body_raw,
            keep_blank_values=True,
        )

        body = {key: values[-1] for key, values in parsed.items()}

        received_requests.append(dict(body))

        pcursor = body.get(
            "pcursor",
            "",
        )

        if pcursor == "":
            comments = _make_comments(
                start=1,
                amount=20,
            )

            next_cursor = "CURSOR_PAGINA_2"

        elif pcursor == "CURSOR_PAGINA_2":
            comments = _make_comments(
                start=21,
                amount=20,
            )

            next_cursor = "CURSOR_PAGINA_3"

        elif pcursor == "CURSOR_PAGINA_3":
            comments = _make_comments(
                start=41,
                amount=10,
            )

            next_cursor = "no_more"

        else:
            raise AssertionError(f"pcursor inesperado: {pcursor!r}")

        # IMPORTANTE:
        #
        # get_root_comments() procura:
        #
        #     data["rootComments"]
        #
        # e get_pcursor() procura:
        #
        #     data["pcursor"]
        #
        # Portanto o mock precisa respeitar
        # exatamente esse formato.
        payload = {
            "result": 1,
            "pcursor": next_cursor,
            "rootComments": comments,
        }

        return httpx.Response(
            status_code=200,
            json=payload,
            request=request,
        )

    transport = httpx.MockTransport(handler)

    http_client = httpx.Client(
        transport=transport,
    )

    client = LiveCommentClient(
        auth_provider=auth_provider,
        client=http_client,
    )

    try:
        comments = client.fetch_root_comments(
            photo_id=("5206029805448533703"),
            user_id="TEST_USER",
            max_comments=50,
            debug=False,
        )

    finally:
        http_client.close()

    # -------------------------------------------------
    # TOTAL DE COMENTÁRIOS
    # -------------------------------------------------

    assert len(comments) == 50

    # -------------------------------------------------
    # AUTH PROVIDER
    # -------------------------------------------------
    #
    # Para 50 comentários:
    #
    # request 1 -> 20
    # request 2 -> 20
    # request 3 -> 10
    #
    # Portanto prepare() precisa ser chamado
    # três vezes.
    # -------------------------------------------------

    assert len(auth_provider.calls) == 3

    # -------------------------------------------------
    # PCURSORS RECEBIDOS PELO PROVIDER
    # -------------------------------------------------

    cursors = [
        call["body"].get(
            "pcursor",
            "",
        )
        for call in auth_provider.calls
    ]

    assert cursors == [
        "",
        "CURSOR_PAGINA_2",
        "CURSOR_PAGINA_3",
    ]

    # -------------------------------------------------
    # COUNT DE CADA REQUEST
    # -------------------------------------------------

    counts = [call["body"].get("count") for call in auth_provider.calls]

    assert counts == [
        "20",
        "20",
        "10",
    ]

    # -------------------------------------------------
    # REQUESTS HTTP
    # -------------------------------------------------

    assert len(received_requests) == 3

    assert (
        received_requests[0].get(
            "pcursor",
            "",
        )
        == ""
    )

    assert received_requests[1].get("pcursor") == "CURSOR_PAGINA_2"

    assert received_requests[2].get("pcursor") == "CURSOR_PAGINA_3"

    # -------------------------------------------------
    # COUNT ENVIADO AO HTTP
    # -------------------------------------------------

    assert received_requests[0].get("count") == "20"

    assert received_requests[1].get("count") == "20"

    assert received_requests[2].get("count") == "10"


@pytest.mark.parametrize(
    "suffix",
    ["", "/", "?share=1", "#comments"],
)
def test_extract_ids_from_mobile_photo_url(suffix: str) -> None:
    url = f"https://m.kwai.com/photo/123456/987654{suffix}"

    assert extract_ids_from_url(url) == ("987654", "123456")


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://www.kwai.com/@example/video/987654", ("987654", "example")),
        ("https://www.kwai.com/video/987654", ("987654", "unknown")),
        ("https://m.kwai.com/photo/123456/987654bad", None),
    ],
)
def test_extract_ids_retains_video_urls_and_rejects_invalid_photo_ids(
    url: str, expected: tuple[str, str] | None
) -> None:
    assert extract_ids_from_url(url) == expected


@pytest.mark.parametrize(
    "payload",
    [
        {"result": 0},
        {"result": 8, "error_msg": ""},
        {"result": None},
        {"result": 1, "error_msg": "Session expired"},
        {"error_msg": "Session expired"},
    ],
)
def test_live_comment_client_rejects_api_errors_even_without_error_message(
    payload: dict[str, object],
) -> None:
    provider = RecordingAuthProvider()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload, request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        client = LiveCommentClient(auth_provider=provider, client=http_client)
        with pytest.raises(RuntimeError, match="A API mobile rejeitou"):
            client.fetch_root_comments("987654", "123456", 20)

    assert len(provider.calls) == 1


@pytest.mark.parametrize("result", [1, None])
def test_live_comment_client_accepts_success_and_legacy_payloads(
    result: int | None,
) -> None:
    payload: dict[str, object] = {
        "rootComments": [{"commentId": "comment-1"}],
        "pcursor": "no_more",
    }
    if result is not None:
        payload["result"] = result

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload, request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        client = LiveCommentClient(
            auth_provider=RecordingAuthProvider(), client=http_client
        )
        assert client.fetch_root_comments("987654", "123456", 20) == [
            {"commentId": "comment-1"}
        ]

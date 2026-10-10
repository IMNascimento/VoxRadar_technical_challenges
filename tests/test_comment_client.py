import httpx

from kwai_collector.clients import comment_client


def handler(
    request: httpx.Request,
) -> httpx.Response:
    assert request.url.path == (comment_client.ROOT_COMMENTS_ENDPOINT)

    return httpx.Response(
        status_code=200,
        json={
            "result": 1,
            "rootComments": [
                {
                    "commentId": "987654321",
                    "userName": "usuario_teste",
                    "kwaiid": "usuario123",
                    "content": "Comentário de teste",
                    "commentLikeCount": 10,
                    "commentTime": 1726000000,
                    "subCommentCount": 0,
                    "subComments": [],
                }
            ],
            "cursor": "no_more",
        },
    )


def test_get_comments() -> None:
    transport = httpx.MockTransport(handler)

    with httpx.Client(
        base_url=comment_client.BASE_URL,
        transport=transport,
    ) as client:
        comentarios, cursor = comment_client.get_comments(
            photo_id="1234567890",
            client=client,
        )

    assert len(comentarios) == 1
    assert comentarios[0]["commentId"] == "987654321"
    assert comentarios[0]["userName"] == "usuario_teste"
    assert comentarios[0]["content"] == "Comentário de teste"
    assert comentarios[0]["commentLikeCount"] == 10
    assert cursor == "no_more"

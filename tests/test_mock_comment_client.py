import httpx

from kwai_collector.clients.mock_comment_client import (
    MockCommentClient,
)


class FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return {
            "result": 1,
            "comments": [
                {
                    "id": "1",
                    "texto": "Comentário teste",
                }
            ],
        }


def test_mock_comment_client_envia_request(
    monkeypatch,
):
    chamada: dict[str, object] = {}

    def fake_post(
        self,
        url,
        *,
        params=None,
        data=None,
        headers=None,
        **kwargs,
    ):
        chamada["url"] = url
        chamada["params"] = params
        chamada["data"] = data
        chamada["headers"] = headers

        return FakeResponse()

    monkeypatch.setattr(
        httpx.Client,
        "post",
        fake_post,
    )

    client = MockCommentClient(
        base_url="http://localhost:8000",
    )

    resultado = client.post(
        endpoint="/mock/comments",
        query={
            "did": "did_teste",
            "lat": "-20",
            "lon": "-43",
            "client_salt": "salt_teste",
            "count": "5",
        },
        body={
            "photo_id": "123",
            "count": "10",
        },
    )

    assert resultado["result"] == 1

    assert chamada["url"] == "http://localhost:8000/mock/comments"

    params = chamada["params"]

    assert isinstance(
        params,
        dict,
    )

    assert "lat" not in params
    assert "lon" not in params
    assert "client_salt" not in params
    assert "count" not in params

    data = chamada["data"]

    assert isinstance(
        data,
        dict,
    )

    assert data["photo_id"] == "123"
    assert data["count"] == "10"
    assert "__MOCK_NS_sig3" in data

    headers = chamada["headers"]

    assert isinstance(
        headers,
        dict,
    )

    assert headers["X-Mock-Signature"] == data["__MOCK_NS_sig3"]

    assert len(str(data["__MOCK_NS_sig3"])) == 32

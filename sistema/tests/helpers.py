"""Fakes e builders compartilhados pelos testes (sem rede de verdade)."""


class FakeResponse:
    def __init__(self, json_data=None, status_code=200, text="", json_error=None, chunks=()):
        self._json = json_data
        self._json_error = json_error
        self.status_code = status_code
        self.text = text
        self._chunks = chunks

    def json(self):
        if self._json_error:
            raise self._json_error
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(f"HTTP {self.status_code}")

    def iter_content(self, chunk_size=None):
        return iter(self._chunks)


class FakeHttp:
    """Substitui uma funcao de request (`post`/`get`): devolve as respostas
    enfileiradas na ordem (ou levanta, se o item for uma excecao) e registra
    cada chamada em `self.calls` como (url, kwargs)."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if not self.responses:
            raise AssertionError(f"chamada HTTP inesperada: {url}")
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def feed_item(photo_id="111", kwai_id="fulano", **extra):
    item = {
        "photo_id_str": photo_id,
        "kwai_id": kwai_id,
        "user_id": 42,
        "caption": f"legenda {photo_id}",
        "like_count": 10,
        "comment_count": 2,
        "forward_count": 1,
        "view_count": 100,
        "timestamp": 1_700_000_000_000,
        "main_mv_urls": [{"url": f"https://cdn/{photo_id}.mp4"}],
        "cover_thumbnail_urls": [{"url": f"https://cdn/{photo_id}.webp"}],
    }
    item.update(extra)
    return item

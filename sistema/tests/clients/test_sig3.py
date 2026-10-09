import pytest
import requests

from kwai_collector import config, sig3
from kwai_collector.errors import Sig3ServiceUnavailableError

from tests.helpers import FakeHttp, FakeResponse

BASE = "http://sig3.test:1234"


@pytest.fixture(autouse=True)
def base_url(monkeypatch):
    monkeypatch.setattr(config, "SIG3_SERVICE_URL", BASE)


@pytest.fixture
def http(monkeypatch):
    def install(get=(), post=()):
        g, p = FakeHttp(*get), FakeHttp(*post)
        monkeypatch.setattr(sig3.requests, "get", g)
        monkeypatch.setattr(sig3.requests, "post", p)
        return g, p

    return install


@pytest.mark.parametrize(
    "resposta,esperado",
    [
        (FakeResponse(text="ok"), True),
        (FakeResponse(text="nao"), False),
        (FakeResponse(text="ok", status_code=500), False),
        (requests.ConnectionError("down"), False),
        (requests.Timeout("lento"), False),
    ],
)
def test_health(http, resposta, esperado):
    http(get=[resposta])
    assert sig3._health(BASE, 1) is esperado


def test_sign_204_devolve_none(http):
    http(post=[FakeResponse(status_code=204)])
    assert sig3._sign(BASE, 1, "abc") is None


def test_sign_erro_http_levanta(http):
    http(post=[FakeResponse(status_code=500)])
    with pytest.raises(requests.HTTPError):
        sig3._sign(BASE, 1, "abc")


def test_assinar_sucesso_envia_string_utf8_no_corpo(http):
    g, p = http(get=[FakeResponse(text="ok")], post=[FakeResponse(text="deadbeef")])
    assert sig3.assinar("POST&/x&ção") == "deadbeef"
    assert g.calls[0][0] == f"{BASE}/health"
    url, kw = p.calls[0]
    assert url == f"{BASE}/sign"
    assert kw["data"] == "POST&/x&ção".encode("utf-8")
    assert kw["timeout"] == config.HTTP_TIMEOUT_SECONDS


def test_assinar_servico_fora_do_ar_da_mensagem_com_instrucao(http):
    _, p = http(get=[requests.ConnectionError("down")])
    with pytest.raises(Sig3ServiceUnavailableError, match="run.bat --serve 8765") as exc:
        sig3.assinar("x")
    assert BASE in str(exc.value)
    assert p.calls == []  # nem tenta assinar


def test_assinar_erro_na_assinatura_vira_servico_indisponivel(http):
    http(get=[FakeResponse(text="ok")], post=[requests.ConnectionError("caiu")])
    with pytest.raises(Sig3ServiceUnavailableError, match="erro ao chamar"):
        sig3.assinar("x")


@pytest.mark.parametrize("resp", [FakeResponse(status_code=204), FakeResponse(text="")])
def test_assinar_resultado_vazio(http, resp):
    http(get=[FakeResponse(text="ok")], post=[resp])
    with pytest.raises(Sig3ServiceUnavailableError, match="vazio"):
        sig3.assinar("x")

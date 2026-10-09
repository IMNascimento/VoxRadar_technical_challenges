import pytest
import requests

from kwai_collector import midia

from tests.helpers import FakeHttp, FakeResponse


@pytest.fixture(autouse=True)
def sem_espera(monkeypatch):
    monkeypatch.setattr(midia.time, "sleep", lambda s: None)


def postagem(video="https://cdn/a/video.mp4?tag=1", thumb="https://cdn/a/thumb.webp"):
    return {"id": "123", "midia": {"video_url": video, "thumbnail_url": thumb}}


@pytest.mark.parametrize(
    "url,padrao,esperado",
    [
        ("https://cdn/a/video.mp4?tag=1-2", ".mp4", ".mp4"),
        ("https://cdn/a/thumb.webp", ".webp", ".webp"),
        ("https://cdn/a/semextensao", ".mp4", ".mp4"),
        ("https://cdn/a/img.jpg", ".webp", ".jpg"),
    ],
)
def test_extensao_midia(url, padrao, esperado):
    assert midia._extensao_midia(url, padrao) == esperado


def test_baixar_arquivo_grava_chunks_ignorando_vazios(monkeypatch, tmp_path):
    fake = FakeHttp(FakeResponse(chunks=[b"ab", b"", b"cd"]))
    monkeypatch.setattr(midia.requests, "get", fake)
    destino = tmp_path / "x" / "y" / "f.bin"

    midia._baixar_arquivo("https://cdn/f", destino)

    assert destino.read_bytes() == b"abcd"
    assert fake.calls[0][1]["stream"] is True


def test_baixar_arquivo_http_erro_levanta_e_nao_cria_arquivo(monkeypatch, tmp_path):
    monkeypatch.setattr(midia.requests, "get", FakeHttp(FakeResponse(status_code=404)))
    destino = tmp_path / "f.bin"
    with pytest.raises(requests.HTTPError):
        midia._baixar_arquivo("https://cdn/f", destino)
    assert not destino.exists()


def test_baixar_midia_estrutura_de_pastas(monkeypatch, tmp_path, capsys):
    fake = FakeHttp(FakeResponse(chunks=[b"video"]), FakeResponse(chunks=[b"thumb"]))
    monkeypatch.setattr(midia.requests, "get", fake)

    midia.baixar_midia(postagem(), tmp_path)

    assert (tmp_path / "media" / "video" / "video.mp4").read_bytes() == b"video"
    assert (tmp_path / "media" / "img" / "thumbnail.webp").read_bytes() == b"thumb"
    assert [c[0] for c in fake.calls] == ["https://cdn/a/video.mp4?tag=1", "https://cdn/a/thumb.webp"]
    assert "[ok] video salvo" in capsys.readouterr().out


def test_baixar_midia_urls_ausentes_avisam_e_nao_baixam(monkeypatch, tmp_path, capsys):
    fake = FakeHttp()
    monkeypatch.setattr(midia.requests, "get", fake)

    midia.baixar_midia({"id": "9", "midia": {"video_url": None}}, tmp_path)
    midia.baixar_midia({"id": "9"}, tmp_path)

    err = capsys.readouterr().err
    assert err.count("indisponivel para 9") == 4
    assert fake.calls == []


def test_baixar_midia_sem_id_usa_sem_id_no_aviso(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(midia.requests, "get", FakeHttp())
    midia.baixar_midia({}, tmp_path)
    assert "sem_id" in capsys.readouterr().err


def test_baixar_midia_falha_num_arquivo_nao_impede_o_outro(monkeypatch, tmp_path, capsys):
    fake = FakeHttp(requests.ConnectionError("down"), FakeResponse(chunks=[b"thumb"]))
    monkeypatch.setattr(midia.requests, "get", fake)

    midia.baixar_midia(postagem(), tmp_path)  # nao levanta

    assert not (tmp_path / "media" / "video" / "video.mp4").exists()
    assert (tmp_path / "media" / "img" / "thumbnail.webp").read_bytes() == b"thumb"
    assert "nao foi possivel baixar video" in capsys.readouterr().err

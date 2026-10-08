"""Testes da CLI (Typer) com HTTP mockado."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from typer.testing import CliRunner

from src.entrypoints.cli import app
from src.infrastructure.mobile_client import (
    COMMENT_FALLBACK_HOSTS,
    COMMENT_HOST,
    COMMENT_PATH,
    PROFILE_FEED_PATH,
    SUBLIST_PATH,
    USER_INFO_PATH,
)
from src.infrastructure.web_client import SEARCH_PATH

BASE = "https://www.kwai.com"
runner = CliRunner()
# Sem rate limit e sem retries: a falha simulada é imediata e o teste não dorme.
_ENV_RAPIDO = {"KWAI_REQUEST_DELAY": "0", "KWAI_MAX_RETRIES": "0"}


def test_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "busca" in result.stdout
    assert "usuario" in result.stdout
    assert "comentarios" in result.stdout


@respx.mock
def test_busca_grava_arquivo(tmp_path: Path, search_response: dict[str, Any]) -> None:
    respx.post(BASE + SEARCH_PATH).mock(return_value=httpx.Response(200, json=search_response))
    out = tmp_path / "busca.json"
    result = runner.invoke(app, ["busca", "-k", "sports", "-l", "5", "-o", str(out)])
    assert result.exit_code == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert isinstance(data, list) and data
    assert data[0]["url"].startswith("https://www.kwai.com/@")
    assert "engajamento" in data[0]


@respx.mock
def test_busca_erro_de_negocio_exit_1(search_response: dict[str, Any]) -> None:
    respx.post(BASE + SEARCH_PATH).mock(
        return_value=httpx.Response(200, json={"result": 11, "error_msg": "erro"})
    )
    result = runner.invoke(app, ["busca", "-k", "sports"])
    assert result.exit_code == 1


def test_comentarios_url_invalida_exit_2() -> None:
    result = runner.invoke(app, ["comentarios", "--url", "https://www.kwai.com/@perfil"])
    assert result.exit_code == 2


def test_busca_configuracao_invalida_exit_1() -> None:
    """``KWAI_HTTP_TIMEOUT`` não numérico falha na configuração (exit 1, sem rede)."""
    result = runner.invoke(app, ["busca", "-k", "sports"], env={"KWAI_HTTP_TIMEOUT": "abc"})
    assert result.exit_code == 1


@respx.mock
def test_comentarios_com_respostas_grava_lista_plana(tmp_path: Path) -> None:
    """``--com-respostas`` acha raiz e resposta numa lista plana com vínculo."""
    respx.post(COMMENT_HOST + COMMENT_PATH).mock(
        return_value=httpx.Response(
            200,
            json={
                "result": 1,
                "pcursor": "no_more",
                "rootComments": [
                    {
                        "comment_id": "r1",
                        "content": "raiz",
                        "author_name": "Quem comenta",
                        "author_id": "a1",
                        "sub_comment_count": 1,
                        "timestamp": 1720226579842,
                    }
                ],
            },
        )
    )
    respx.post(COMMENT_HOST + SUBLIST_PATH).mock(
        return_value=httpx.Response(
            200,
            json={
                "result": 1,
                "pcursor": "no_more",
                "subComments": [
                    {
                        "comment_id": "s1",
                        "content": "resposta",
                        "author_name": "Quem responde",
                        "author_id": "a2",
                        "reply_to": 150001404765512,
                        "replyToUserName": "Quem comenta",
                        "timestamp": 1720226579842,
                    }
                ],
            },
        )
    )
    out = tmp_path / "comentarios.json"

    result = runner.invoke(
        app,
        [
            "comentarios",
            "--url",
            "https://www.kwai.com/@perfil/video/123",
            "--com-respostas",
            "-o",
            str(out),
        ],
        env={"KWAI_REQUEST_DELAY": "0"},
    )

    assert result.exit_code == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert [item["id"] for item in data] == ["r1", "s1"]
    assert data[0]["parent_id"] is None
    assert data[0]["respostas_total"] == 1
    assert data[1]["parent_id"] == "r1"
    assert data[1]["reply_to_usuario"] == "Quem comenta"


def _feed_page(ids: list[str], pcursor: str) -> dict[str, Any]:
    return {
        "result": 1,
        "pcursor": pcursor,
        "feeds": [
            {
                "photo_id_str": pid,
                "kwai_id": "perfil_teste",
                "like_count": 1,
                "timestamp": 1_700_000_000_000,
            }
            for pid in ids
        ],
    }


def _mock_user_info() -> None:
    respx.post(COMMENT_HOST + USER_INFO_PATH).mock(
        return_value=httpx.Response(
            200, json={"result": 1, "users": [{"user_id": 150001214685137}]}
        )
    )


@respx.mock
def test_usuario_falha_no_meio_grava_o_parcial_e_sai_com_1(tmp_path: Path) -> None:
    """Uma falha na 2ª página não pode jogar fora a 1ª: o parcial é gravado (exit 1)."""
    _mock_user_info()
    respx.post(COMMENT_HOST + PROFILE_FEED_PATH).mock(
        side_effect=[
            httpx.Response(200, json=_feed_page(["1", "2"], "PAGE2")),
            httpx.ConnectError("gateway fora do ar"),
        ]
    )
    for host in COMMENT_FALLBACK_HOSTS:
        respx.post(host + PROFILE_FEED_PATH).mock(side_effect=httpx.ConnectError("fora do ar"))
    out = tmp_path / "usuario.json"

    result = runner.invoke(app, ["usuario", "-u", "@perfil_teste", "-o", str(out)], env=_ENV_RAPIDO)

    assert result.exit_code == 1
    data = json.loads(out.read_text(encoding="utf-8"))
    assert [item["id"] for item in data] == ["1", "2"]


@respx.mock
def test_usuario_falha_ao_gravar_o_parcial_sai_com_1_sem_estourar(tmp_path: Path) -> None:
    """Se nem o parcial pode ser gravado (saída é um diretório), só se registra e sai com 1."""
    _mock_user_info()
    respx.post(COMMENT_HOST + PROFILE_FEED_PATH).mock(
        side_effect=[
            httpx.Response(200, json=_feed_page(["1"], "PAGE2")),
            httpx.ConnectError("gateway fora do ar"),
        ]
    )
    for host in COMMENT_FALLBACK_HOSTS:
        respx.post(host + PROFILE_FEED_PATH).mock(side_effect=httpx.ConnectError("fora do ar"))

    result = runner.invoke(
        app, ["usuario", "-u", "@perfil_teste", "-o", str(tmp_path)], env=_ENV_RAPIDO
    )

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)


@respx.mock
def test_usuario_falha_sem_nada_coletado_nao_cria_arquivo(tmp_path: Path) -> None:
    for host in (COMMENT_HOST, *COMMENT_FALLBACK_HOSTS):
        respx.post(host + USER_INFO_PATH).mock(side_effect=httpx.ConnectError("fora do ar"))
    out = tmp_path / "usuario.json"

    result = runner.invoke(app, ["usuario", "-u", "@perfil_teste", "-o", str(out)], env=_ENV_RAPIDO)

    assert result.exit_code == 1
    assert not out.exists()


@pytest.mark.parametrize(
    ("code", "hint"),
    [
        (50, "assinatura"),
        (11, "contexto"),
        (40, "client_key"),
    ],
)
@respx.mock
def test_api_error_reports_orientation_without_claiming_exact_cause(
    code: int,
    hint: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    respx.post(COMMENT_HOST + USER_INFO_PATH).mock(
        return_value=httpx.Response(200, json={"result": code, "error_msg": "original API message"})
    )
    result = runner.invoke(app, ["usuario", "-u", "@perfil"], env=_ENV_RAPIDO)
    assert result.exit_code == 1
    assert "original API message" in caplog.text
    assert f"result={code}" in caplog.text
    assert USER_INFO_PATH in caplog.text
    assert hint in caplog.text
    assert "causa exata não determinada" in caplog.text


@respx.mock
def test_unknown_api_code_does_not_invent_signature_diagnosis(
    caplog: pytest.LogCaptureFixture,
) -> None:
    respx.post(COMMENT_HOST + USER_INFO_PATH).mock(
        return_value=httpx.Response(200, json={"result": 987, "error_msg": "unknown API error"})
    )
    result = runner.invoke(app, ["usuario", "-u", "@perfil"], env=_ENV_RAPIDO)
    assert result.exit_code == 1
    assert "unknown API error" in caplog.text
    assert "result=987" in caplog.text
    assert "sal" not in caplog.text


@respx.mock
def test_comments_malformed_second_page_writes_partial(tmp_path: Path) -> None:
    respx.post(COMMENT_HOST + COMMENT_PATH).mock(
        side_effect=[
            httpx.Response(
                200,
                json={
                    "result": 1,
                    "pcursor": "NEXT",
                    "rootComments": [{"comment_id": "r1", "content": "valid"}],
                },
            ),
            httpx.Response(200, json={"result": 1, "pcursor": "no_more", "rootComments": [None]}),
        ]
    )
    out = tmp_path / "partial.json"
    result = runner.invoke(
        app,
        [
            "comentarios",
            "--url",
            "https://www.kwai.com/@perfil/video/123",
            "-o",
            str(out),
        ],
        env=_ENV_RAPIDO,
    )
    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert [item["id"] for item in json.loads(out.read_text(encoding="utf-8"))] == ["r1"]


@respx.mock
def test_comments_malformed_first_page_does_not_create_output(tmp_path: Path) -> None:
    respx.post(COMMENT_HOST + COMMENT_PATH).mock(
        return_value=httpx.Response(
            200, json={"result": 1, "pcursor": "no_more", "rootComments": [None]}
        )
    )
    out = tmp_path / "missing.json"
    result = runner.invoke(
        app,
        [
            "comentarios",
            "--url",
            "https://www.kwai.com/@perfil/video/123",
            "-o",
            str(out),
        ],
        env=_ENV_RAPIDO,
    )
    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert not out.exists()


@respx.mock
def test_signature_rejection_after_first_page_reports_hint_and_saves_partial(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _mock_user_info()
    route = respx.post(COMMENT_HOST + PROFILE_FEED_PATH).mock(
        side_effect=[
            httpx.Response(200, json=_feed_page(["1"], "NEXT")),
            httpx.Response(200, json={"result": 50, "error_msg": "signature rejected"}),
        ]
    )
    out = tmp_path / "partial.json"
    result = runner.invoke(app, ["usuario", "-u", "@perfil", "-o", str(out)], env=_ENV_RAPIDO)
    assert result.exit_code == 1
    assert [item["id"] for item in json.loads(out.read_text(encoding="utf-8"))] == ["1"]
    assert "signature rejected" in caplog.text
    assert "causa exata não determinada" in caplog.text
    assert len(route.calls) == 2

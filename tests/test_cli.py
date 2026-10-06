"""Testes da CLI (Typer) com HTTP mockado."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import respx
from typer.testing import CliRunner

from src.entrypoints.cli import app
from src.infrastructure.mobile_client import COMMENT_HOST, COMMENT_PATH, SUBLIST_PATH
from src.infrastructure.web_client import SEARCH_PATH

BASE = "https://www.kwai.com"
runner = CliRunner()


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

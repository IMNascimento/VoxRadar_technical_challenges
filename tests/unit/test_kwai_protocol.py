"""Testes das regras de protocolo e de valores crus do Kwai na infraestrutura (sem rede)."""

from __future__ import annotations

import pytest

from src.infrastructure.kwai.business_result import ensure_business_success
from src.infrastructure.kwai.coercion import as_int_scalar
from src.infrastructure.kwai.exceptions import KwaiApiError
from src.infrastructure.kwai.http_utils import read_cursor

# --- coercion ---------------------------------------------------------------


def test_as_int_scalar_aceita_int_str_numerica_e_float() -> None:
    assert as_int_scalar(7) == 7
    assert as_int_scalar("42") == 42
    assert as_int_scalar(3.9) == 3


def test_as_int_scalar_rejeita_bool_none_e_nao_escalares() -> None:
    assert as_int_scalar(True) is None
    assert as_int_scalar(False) is None
    assert as_int_scalar(None) is None
    assert as_int_scalar("abc") is None
    assert as_int_scalar("12.5") is None
    assert as_int_scalar([1]) is None
    assert as_int_scalar({"a": 1}) is None


@pytest.mark.parametrize("value", [float("inf"), float("-inf"), float("nan")])
def test_as_int_scalar_rejects_non_finite_numbers(value: float) -> None:
    assert as_int_scalar(value) is None


# --- pcursor ----------------------------------------------------------------


@pytest.mark.parametrize("value", ["no_more", "nomore", "-1", "0", 0, -1, "", None])
def test_read_cursor_traduz_sentinelas_de_fim_para_vazio(value: object) -> None:
    assert read_cursor({"pcursor": value}, source="/rota") == ""


def test_read_cursor_ausente_vira_vazio() -> None:
    assert read_cursor({}, source="/rota") == ""


def test_read_cursor_preserva_cursor_de_continuacao() -> None:
    assert read_cursor({"pcursor": "PAGE2"}, source="/rota") == "PAGE2"
    assert read_cursor({"pcursor": 1727287362050}, source="/rota") == "1727287362050"


# --- business_result --------------------------------------------------------

_WEB_DEFAULT_MESSAGE = "erro de negócio da API do Kwai"
_MOBILE_DEFAULT_MESSAGE = "erro de negócio da API móvel do Kwai"


def test_ensure_business_success_passa_com_result_1_e_sem_result() -> None:
    ensure_business_success({"result": 1}, default_message=_MOBILE_DEFAULT_MESSAGE)
    ensure_business_success({}, default_message=_MOBILE_DEFAULT_MESSAGE)


def test_ensure_business_success_web_monta_mensagem_com_source() -> None:
    with pytest.raises(KwaiApiError) as exc:
        ensure_business_success(
            {"result": 2},
            default_message=_WEB_DEFAULT_MESSAGE,
            source="/rest/o/w",
        )
    assert str(exc.value) == "erro de negócio da API do Kwai (result=2) em /rest/o/w"
    assert exc.value.result == 2


def test_ensure_business_success_movel_monta_mensagem_sem_source() -> None:
    with pytest.raises(KwaiApiError) as exc:
        ensure_business_success({"result": 2}, default_message=_MOBILE_DEFAULT_MESSAGE)
    assert str(exc.value) == "erro de negócio da API móvel do Kwai (result=2)"
    assert exc.value.result == 2


def test_ensure_business_success_usa_error_msg_quando_presente() -> None:
    with pytest.raises(KwaiApiError) as exc:
        ensure_business_success(
            {"result": 11, "error_msg": "param"},
            default_message=_WEB_DEFAULT_MESSAGE,
            source="/rest/a",
        )
    assert str(exc.value) == "param (result=11) em /rest/a"

"""Testes das regras puras de domínio (sem I/O, sem mocks)."""

from __future__ import annotations

from datetime import datetime

import pytest

from src.domain.business_result import ensure_business_success
from src.domain.exceptions import InvalidInputError, KwaiApiError
from src.domain.identity import (
    comment_dedup_key,
    extract_photo_id,
    normalize_handle,
    post_dedup_key,
)
from src.domain.value_objects.cursor import Cursor
from src.shared.utils.coercion import as_int_scalar
from src.shared.utils.timestamps import now_iso

# --- pagination -------------------------------------------------------------


def test_cursor_is_end_reconhece_todos_os_valores_de_fim() -> None:
    for cursor in ("", "no_more", "nomore", "-1", "0"):
        assert Cursor(cursor).is_end(), cursor


def test_cursor_is_end_false_para_cursors_reais() -> None:
    assert not Cursor("PAGE2").is_end()
    assert not Cursor("1727287362050").is_end()


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


# --- business_result --------------------------------------------------------

_WEB_DEFAULT_MESSAGE = "erro de negócio da API do Kwai"
_MOBILE_DEFAULT_MESSAGE = "erro de negócio da API móvel do Kwai"


def test_ensure_business_success_passa_com_result_1_e_sem_result() -> None:
    assert ensure_business_success({"result": 1}, default_message=_MOBILE_DEFAULT_MESSAGE) is None
    assert ensure_business_success({}, default_message=_MOBILE_DEFAULT_MESSAGE) is None


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


# --- identity ---------------------------------------------------------------


def test_post_dedup_key_prefere_o_id_e_cai_para_url() -> None:
    assert post_dedup_key("1", "u") == "1"
    assert post_dedup_key(None, "u") == "u"


def test_comment_dedup_key_prefere_o_id() -> None:
    assert comment_dedup_key("c_1", "a_1", "oi") == "c_1"


def test_comment_dedup_key_fallback_autor_id_texto() -> None:
    assert comment_dedup_key(None, "a_1", "oi") == "3:a_1oi"


def test_comment_dedup_key_nao_colide_com_separador_ambiguo() -> None:
    assert comment_dedup_key(None, "a:b", "c") != comment_dedup_key(None, "a", "b:c")
    assert comment_dedup_key(None, "a\x00b", "c") != comment_dedup_key(None, "a", "b\x00c")


def test_normalize_handle_remove_arroba_e_espacos_das_bordas() -> None:
    assert normalize_handle("@perfil").value == "perfil"
    assert normalize_handle(" perfil ").value == "perfil"
    assert normalize_handle(" @a.b_c ").value == "a.b_c"


def test_normalize_handle_erro_para_conta_vazia() -> None:
    with pytest.raises(InvalidInputError):
        normalize_handle("   ")
    with pytest.raises(InvalidInputError):
        normalize_handle("@")


def test_normalize_handle_erro_para_barra_ou_espaco_interno() -> None:
    with pytest.raises(InvalidInputError) as barra:
        normalize_handle("perfil/x")
    with pytest.raises(InvalidInputError) as espaco:
        normalize_handle("perfil x")
    assert "perfil/x" in str(barra.value)
    assert "perfil x" in str(espaco.value)


def test_extract_photo_id_video_e_photo() -> None:
    assert extract_photo_id("https://www.kwai.com/@p/video/123").value == "123"
    assert extract_photo_id("https://www.kwai.com/@p/photo/999").value == "999"


def test_extract_photo_id_erro_para_url_sem_id() -> None:
    with pytest.raises(InvalidInputError) as exc:
        extract_photo_id("https://www.kwai.com/@perfil")
    assert "URL de postagem inválida" in str(exc.value)
    assert "/video/" in str(exc.value) and "/photo/" in str(exc.value)


# --- timestamps -------------------------------------------------------------


def test_now_iso_tem_formato_iso_utc() -> None:
    stamp = now_iso()
    datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ")
    assert stamp.endswith("Z")

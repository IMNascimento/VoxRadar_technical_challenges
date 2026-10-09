"""Testes das regras puras de domínio (sem I/O, sem mocks)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from src.domain.entities.post import Engagement, Post
from src.domain.exceptions.domain_exceptions import InvalidInputError, InvalidValueError
from src.domain.services.identity import (
    UniqueItems,
    comment_dedup_key,
    normalize_handle,
    post_dedup_key,
    unique_posts,
)
from src.domain.services.post_urls import (
    extract_photo_id,
    parse_post_reference,
    post_url,
    profile_url,
)
from src.domain.services.replies import declares_replies, replies_diverge
from src.domain.value_objects.cursor import Cursor
from src.domain.value_objects.iso_timestamp import IsoTimestamp

# --- pagination -------------------------------------------------------------


def test_cursor_vazio_marca_o_fim() -> None:
    assert Cursor("").is_end()


def test_cursor_is_end_false_para_cursors_reais() -> None:
    assert not Cursor("PAGE2").is_end()
    assert not Cursor("1727287362050").is_end()
    assert not Cursor("no_more").is_end()


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


def test_unique_items_mantem_a_primeira_ocorrencia_entre_lotes() -> None:
    unique: UniqueItems[str] = UniqueItems(str.lower)

    assert list(unique.filter(["a", "B", "A"])) == ["a", "B"]
    assert list(unique.filter(["b", "c"])) == ["c"]
    assert not unique.add("C")


def test_unique_posts_usa_o_id_e_cai_para_a_url() -> None:
    def post(post_id: str | None, url: str) -> Post:
        return Post(id=post_id, url=url, engajamento=Engagement(), coletado_em="x")

    posts = [post("1", "u1"), post("1", "u2"), post(None, "u3"), post(None, "u3")]

    assert [(p.id, p.url) for p in unique_posts().filter(posts)] == [("1", "u1"), (None, "u3")]


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


# --- post_urls --------------------------------------------------------------


def test_post_url_e_profile_url_canonicas() -> None:
    assert profile_url("perfil") == "https://www.kwai.com/@perfil"
    assert post_url("perfil", "123") == "https://www.kwai.com/@perfil/video/123"


def test_extract_photo_id_video_e_photo() -> None:
    assert extract_photo_id("https://www.kwai.com/@p/video/123").value == "123"
    assert extract_photo_id("https://www.kwai.com/@p/photo/999").value == "999"


def test_extract_photo_id_erro_para_url_sem_id() -> None:
    with pytest.raises(InvalidInputError) as exc:
        extract_photo_id("https://www.kwai.com/@perfil")
    assert "URL de postagem inválida" in str(exc.value)
    assert "/video/" in str(exc.value) and "/photo/" in str(exc.value)


def test_parse_post_reference_extrai_id_e_dono() -> None:
    post = parse_post_reference("https://www.kwai.com/@perfil%20x/video/123?x=1")

    assert post.photo_id.value == "123"
    assert post.owner == "perfil x"


def test_parse_post_reference_sem_segmento_de_dono() -> None:
    assert parse_post_reference("https://www.kwai.com/photo/999").owner is None
    assert parse_post_reference("https://www.kwai.com/@/video/1").owner is None


# --- replies ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("declared", "expected"), [(None, False), (0, False), (3, True), (-1, True)]
)
def test_declares_replies_usa_truthiness(declared: int | None, expected: bool) -> None:
    assert declares_replies(declared) is expected


@pytest.mark.parametrize(
    ("declared", "collected", "expected"),
    [(5, 3, True), (2, 4, True), (3, 3, False), (None, 3, False), (-1, 0, False)],
)
def test_replies_diverge_so_compara_total_conhecido_e_nao_negativo(
    declared: int | None, collected: int, expected: bool
) -> None:
    assert replies_diverge(declared, collected) is expected


# --- timestamps -------------------------------------------------------------


def test_iso_timestamp_from_datetime_converte_para_utc_em_segundos() -> None:
    moment = datetime(2026, 10, 9, 12, 30, 15, 999_000, tzinfo=timezone(timedelta(hours=-3)))

    assert IsoTimestamp.from_datetime(moment).value == "2026-10-09T15:30:15Z"
    assert IsoTimestamp.from_datetime(datetime.now(tz=UTC)).value.endswith("Z")


@pytest.mark.parametrize(
    "value",
    [
        "2026-99-99T25:61:61Z",
        "2026-02-29T00:00:00Z",
        "2026-04-31T00:00:00Z",
        "2026-10-09T24:00:00Z",
        "2026-10-09T00:60:00Z",
        "2026-10-09T00:00:60Z",
        "2026-10-09",
    ],
)
def test_iso_timestamp_rejeita_data_ou_horario_invalido(value: str) -> None:
    with pytest.raises(InvalidValueError, match="timestamp ISO-8601 UTC inválido"):
        IsoTimestamp(value)


def test_iso_timestamp_aceita_dia_bissexto_valido() -> None:
    value = "2024-02-29T23:59:59Z"

    assert IsoTimestamp(value).value == value


def test_iso_timestamp_from_datetime_rejeita_instante_sem_fuso() -> None:
    with pytest.raises(InvalidValueError, match="fuso"):
        IsoTimestamp.from_datetime(datetime(2026, 10, 9, 12, 30, 15))

"""Testes das regras puras de domínio (sem I/O, sem mocks)."""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime, timedelta, timezone

import pytest

from src.domain.entities.comment import Comment, CommentAuthor
from src.domain.entities.post import Engagement, Post
from src.domain.enums.post_sort_by import PostSortBy
from src.domain.exceptions.domain_exceptions import InvalidInputError, InvalidValueError
from src.domain.services.identity import UniqueItems, unique_comments, unique_posts
from src.domain.services.post_urls import (
    extract_photo_id,
    parse_post_reference,
    post_url,
    profile_url,
)
from src.domain.services.replies import declares_replies, replies_diverge
from src.domain.value_objects.cursor import Cursor
from src.domain.value_objects.identifiers import Handle
from src.domain.value_objects.iso_timestamp import IsoTimestamp

# --- pagination -------------------------------------------------------------


def test_cursor_vazio_marca_o_fim() -> None:
    assert Cursor("").is_end()


def test_cursor_is_end_false_para_cursors_reais() -> None:
    assert not Cursor("PAGE2").is_end()
    assert not Cursor("1727287362050").is_end()
    assert not Cursor("no_more").is_end()


# --- identity ---------------------------------------------------------------


def _post(post_id: str | None, url: str) -> Post:
    return Post(id=post_id, url=url, engajamento=Engagement(), coletado_em="x")


def _comment(comment_id: str | None, author_id: str | None, text: str) -> Comment:
    return Comment(
        id=comment_id,
        postagem_url="u",
        autor=CommentAuthor(id=author_id),
        texto=text,
        coletado_em="x",
    )


def test_post_dedup_key_prefere_o_id_e_cai_para_url() -> None:
    assert _post("1", "u").dedup_key == "1"
    assert _post(None, "u").dedup_key == "u"


def test_comment_dedup_key_prefere_o_id() -> None:
    assert _comment("c_1", "a_1", "oi").dedup_key == "c_1"


def test_comment_dedup_key_fallback_autor_id_texto() -> None:
    assert _comment(None, "a_1", "oi").dedup_key == "3:a_1oi"
    assert _comment(None, None, "oi").dedup_key == "0:oi"


def test_comment_dedup_key_nao_colide_com_separador_ambiguo() -> None:
    assert _comment(None, "a:b", "c").dedup_key != _comment(None, "a", "b:c").dedup_key
    assert _comment(None, "a\x00b", "c").dedup_key != _comment(None, "a", "b\x00c").dedup_key


def test_dedup_key_nao_entra_no_contrato_serializado() -> None:
    assert "dedup_key" not in asdict(_post("1", "u"))
    assert "dedup_key" not in asdict(_comment("c_1", "a_1", "oi"))


def test_unique_comments_usa_a_identidade_do_comentario() -> None:
    comments = [_comment("c_1", "a", "x"), _comment("c_1", "b", "y"), _comment(None, "a", "x")]

    assert [c.texto for c in unique_comments().filter(comments)] == ["x", "x"]


def test_engagement_count_le_a_contagem_pedida() -> None:
    engagement = Engagement(curtidas=1, comentarios=2, compartilhamentos=3)

    assert [engagement.count(metric) for metric in PostSortBy] == [1, 2, 3, None]


def test_unique_items_mantem_a_primeira_ocorrencia_entre_lotes() -> None:
    unique: UniqueItems[str] = UniqueItems(str.lower)

    assert list(unique.filter(["a", "B", "A"])) == ["a", "B"]
    assert list(unique.filter(["b", "c"])) == ["c"]
    assert not unique.add("C")


def test_unique_posts_usa_o_id_e_cai_para_a_url() -> None:
    posts = [_post("1", "u1"), _post("1", "u2"), _post(None, "u3"), _post(None, "u3")]

    assert [(p.id, p.url) for p in unique_posts().filter(posts)] == [("1", "u1"), (None, "u3")]


def test_handle_parse_remove_arroba_e_espacos_das_bordas() -> None:
    assert Handle.parse("@perfil").value == "perfil"
    assert Handle.parse(" perfil ").value == "perfil"
    assert Handle.parse(" @a.b_c ").value == "a.b_c"


def test_handle_parse_erro_para_conta_vazia() -> None:
    with pytest.raises(InvalidInputError):
        Handle.parse("   ")
    with pytest.raises(InvalidInputError):
        Handle.parse("@")


def test_handle_parse_erro_para_barra_ou_espaco_interno() -> None:
    with pytest.raises(InvalidInputError) as barra:
        Handle.parse("perfil/x")
    with pytest.raises(InvalidInputError) as espaco:
        Handle.parse("perfil x")
    assert "perfil/x" in str(barra.value)
    assert "perfil x" in str(espaco.value)


@pytest.mark.parametrize("whitespace", ["\t", "\n", "\r", "\u00a0", "\u2003"])
def test_handle_rejeita_whitespace_interno(whitespace: str) -> None:
    value = f"perfil{whitespace}x"

    with pytest.raises(InvalidInputError, match="usuário inválido"):
        Handle(value)
    with pytest.raises(InvalidInputError, match="usuário inválido"):
        Handle.parse(value)


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

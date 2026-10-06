"""Testes da avaliação do estado SSR (``__NUXT__``) em Python puro."""

from __future__ import annotations

import pytest

from src.domain.exceptions import KwaiCollectorError
from src.infrastructure.exceptions import UnexpectedResponseError
from src.infrastructure.nuxt import (
    FeedsData,
    evaluate_feeds_data,
    evaluate_nuxt,
    extract_nuxt_expression,
)


def test_extract_nuxt_expression(profile_html: str) -> None:
    expr = extract_nuxt_expression(profile_html)
    assert expr.startswith("(function")
    assert "feedsData" in expr


def test_extract_nuxt_expression_ausente() -> None:
    with pytest.raises(KwaiCollectorError):
        extract_nuxt_expression("<html><body>sem estado</body></html>")


def test_evaluate_feeds_data(profile_html: str) -> None:
    data = evaluate_feeds_data(profile_html)
    feeds = data.feeds
    assert len(feeds) == 2
    assert feeds[0]["photo_id_str"] == "5240651225143682227"
    assert feeds[0]["like_count"] == 100
    assert data.cursor == "1727287362050"


def test_evaluate_nuxt_substitui_parametros() -> None:
    # Valores repetidos são fatorados em parâmetros (a, b) e resolvidos por posição.
    expr = '(function(a,b){return {nome:a,eco:a,flag:b,vazio:null,on:!0,off:!1}}("x",42))'
    assert evaluate_nuxt(expr) == {
        "nome": "x",
        "eco": "x",
        "flag": 42,
        "vazio": None,
        "on": True,
        "off": False,
    }


def test_evaluate_nuxt_escapes_e_unicode() -> None:
    expr = r'(function(a){return {t:a}}("linha\nfim / é 😀"))'
    assert evaluate_nuxt(expr) == {"t": "linha\nfim / é 😀"}


def test_evaluate_nuxt_escapes_unicode_e_surrogate() -> None:
    # Escapes JS crus: é (é), par surrogate 😀 (😀) e \x41 (A).
    js_escapes = "\\u00e9\\uD83D\\uDE00\\x41"
    expr = '(function(a){return {a:a}}("' + js_escapes + '"))'
    assert evaluate_nuxt(expr) == {"a": "é\U0001f600A"}


def test_evaluate_nuxt_numeros_e_aspas_simples() -> None:
    expr = "(function(){return {hex:0x1F,exp:1.5e3,txt:'aspas simples'}}())"
    assert evaluate_nuxt(expr) == {"hex": 31, "exp": 1500.0, "txt": "aspas simples"}


def test_evaluate_nuxt_array_com_buraco() -> None:
    # Elisão: [1,,3] tem um buraco que vira None.
    assert evaluate_nuxt("(function(){return {v:[1,,3]}}())") == {"v": [1, None, 3]}


def test_evaluate_nuxt_iife_ausente() -> None:
    with pytest.raises(KwaiCollectorError):
        evaluate_nuxt("(alert(1))")


def test_evaluate_nuxt_void_e_arrays() -> None:
    expr = "(function(){return {u:void 0,lista:[1,2,[3],{}],neg:-5}}())"
    assert evaluate_nuxt(expr) == {"u": None, "lista": [1, 2, [3], {}], "neg": -5}


def test_evaluate_nuxt_objeto_puro_sem_iife() -> None:
    # Estado já serializado como objeto puro (sem wrapper de fatoração).
    assert evaluate_nuxt('{"a":1,"b":"c"}') == {"a": 1, "b": "c"}


def test_evaluate_feeds_data_sem_feeds() -> None:
    html = "<script>window.__NUXT__=(function(){return {data:[{}]}}())</script>"
    assert evaluate_feeds_data(html) == FeedsData(feeds=[])


@pytest.mark.parametrize(
    ("expr", "defeito"),
    [
        ('(function(a){return {t:a}}("sem fecho))', "string não fechada"),
        ('(function(a){return {t:a}} "x")', "IIFE não balanceada"),
        ("{a:}", "valor ausente após ':'"),
    ],
    ids=["string-nao-fechada", "iife-nao-balanceada", "objeto-malformado"],
)
def test_evaluate_nuxt_malformado_levanta_erro(expr: str, defeito: str) -> None:
    """Estado SSR truncado/malformado levanta UnexpectedResponseError, não exceção crua."""
    with pytest.raises(UnexpectedResponseError, match="estado SSR malformado"):
        evaluate_nuxt(expr)

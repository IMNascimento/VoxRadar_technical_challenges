"""Extração do estado SSR do Kwai (``window.__NUXT__``) sem runtime externo.

As postagens de um perfil não vêm de um endpoint JSON anônimo: o endpoint real
(``POST /rest/o/w/pc/feed/profile``) exige **sessão logada** — para visitantes
anônimos ele responde ``result: 11`` (verificado capturando a requisição real da
própria página: URL limpa, apenas cabeçalhos ``Accept``/``Content-Type``, sem
qualquer assinatura). Porém a página do perfil já embute a primeira página de
postagens no estado do Nuxt (``window.__NUXT__``), acessível sem login.

Esse estado é uma IIFE minificada da forma
``(function(a,b,...){return <objeto>}(<args>))``: um *object literal* de JS cujos
valores primitivos repetidos são fatorados em parâmetros da função e passados
como argumentos posicionais. Em vez de avaliá-lo com um interpretador JS
(Node/V8) ou um navegador headless, resolvemos a expressão com um pequeno parser
recursivo em Python puro — sem dependências, sem processos externos e testável
offline. A saída é idêntica à de um ``eval`` real (validado campo a campo).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import TypeAlias

from ..shared.logging_config import get_logger
from .exceptions import UnexpectedResponseError

logger = get_logger("nuxt")

JsonValue: TypeAlias = (
    dict[str, "JsonValue"] | list["JsonValue"] | str | int | float | bool | None
)

_NUXT_RE = re.compile(
    r"window\.__NUXT__\s*=\s*(?P<expr>.*?);?\s*</script>",
    re.DOTALL,
)

_WS = " \t\r\n"
_IDENT = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_$")
# Caracteres que compõem um literal numérico JS (inclui hex e notação científica).
_NUMBER_CHARS = frozenset("0123456789.eExXaAbBcCdDfF+-")
_SIMPLE_ESC = {"n": "\n", "r": "\r", "t": "\t", "b": "\b", "f": "\f", "v": "\v", "0": "\0"}
# Limite de profundidade da busca por ``feedsData`` no estado SSR.
_MAX_FEEDS_DEPTH = 8


class _Ref:
    """Referência a um parâmetro da IIFE, resolvida depois via ``env``."""

    __slots__ = ("name",)

    def __init__(self, name: str) -> None:
        self.name = name


# Árvore do parser: valor JSON cru ou, recursivamente, ``_Ref`` pendente de env.
_Node: TypeAlias = (
    dict[str, "_Node"] | list["_Node"] | str | int | float | bool | None | _Ref
)

_KEYWORDS: dict[str, _Node] = {
    "null": None,
    "undefined": None,
    "true": True,
    "false": False,
    "NaN": float("nan"),
    "Infinity": float("inf"),
}


class _JsLiteralParser:
    """Parser recursivo do subconjunto *data-only* de literais JS do Nuxt."""

    def __init__(self, source: str) -> None:
        self._source = source
        self._position = 0
        self._length = len(source)

    # -- utilitários -----------------------------------------------------------

    def _skip_ws(self) -> None:
        while self._position < self._length and self._source[self._position] in _WS:
            self._position += 1

    def _expect(self, expected: str) -> None:
        if self._position >= self._length or self._source[self._position] != expected:
            raise UnexpectedResponseError(
                f"estado SSR malformado: esperado {expected!r} na posição {self._position}"
            )
        self._position += 1

    # -- expressão completa ----------------------------------------------------

    def parse_expression(self) -> JsonValue:
        """Interpreta a expressão inteira (IIFE fatorada ou objeto puro)."""
        self._skip_ws()
        if self._source[self._position] != "(":
            # Estado já serializado como objeto puro (sem IIFE de fatoração).
            return _resolve(self.parse_value(), {})

        self._expect("(")
        self._skip_ws()
        if self._source[self._position : self._position + 8] != "function":
            raise UnexpectedResponseError("expressão __NUXT__ inesperada (IIFE ausente)")
        self._position += 8
        self._skip_ws()
        self._expect("(")
        params = self._parse_function_params()
        self._skip_ws()
        self._expect("{")
        self._skip_ws()
        if self._source[self._position : self._position + 6] == "return":
            self._position += 6
        body = self.parse_value()  # árvore com placeholders _Ref
        self._skip_ws()
        self._expect("}")
        self._skip_ws()
        self._expect("(")
        args = self._parse_call_args()
        # Argumentos da IIFE são valores do escopo externo: não há env para eles.
        env: dict[str, JsonValue] = {
            name: _resolve(arg, {}) for name, arg in zip(params, args, strict=False)
        }
        return _resolve(body, env)

    def _parse_function_params(self) -> list[str]:
        """Lê os nomes dos parâmetros da IIFE até o ``)`` que a fecha."""
        start = self._position
        depth = 1
        while depth:
            char = self._source[self._position]
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            self._position += 1
        raw_params = self._source[start : self._position - 1]
        return [param.strip() for param in raw_params.split(",") if param.strip()]

    def _parse_call_args(self) -> list[_Node]:
        """Lê os argumentos posicionais da chamada da IIFE até o ``)``."""
        args: list[_Node] = []
        self._skip_ws()
        if self._source[self._position] == ")":
            return args
        while True:
            args.append(self.parse_value())
            self._skip_ws()
            closing = self._source[self._position]
            self._position += 1
            if closing == ")":
                return args

    # -- valores ---------------------------------------------------------------

    def parse_value(self) -> _Node:
        self._skip_ws()
        char = self._source[self._position]
        if char == "{":
            return self._object()
        if char == "[":
            return self._array()
        if char in "\"'":
            return self._string()
        if char == "!":  # booleanos minificados: !0 -> True, !1 -> False
            self._position += 1
            digit = self._source[self._position]
            self._position += 1
            return digit == "0"
        if char == "-" or char == "." or char.isdigit():
            return self._number()
        return self._ident()

    def _object(self) -> dict[str, _Node]:
        self._expect("{")
        obj: dict[str, _Node] = {}
        self._skip_ws()
        if self._source[self._position] == "}":
            self._position += 1
            return obj
        while True:
            self._skip_ws()
            if self._source[self._position] in "\"'":
                key = self._string()
            else:
                start = self._position
                while self._source[self._position] != ":" and self._source[self._position] not in _WS:
                    self._position += 1
                key = self._source[start : self._position]
            self._skip_ws()
            self._expect(":")
            obj[key] = self.parse_value()
            self._skip_ws()
            separator_position = self._position
            separator = self._source[separator_position]
            self._position += 1
            if separator == "}":
                return obj
            if separator != ",":
                raise UnexpectedResponseError(
                    "estado SSR malformado: esperado ',' ou '}' "
                    f"na posição {separator_position}"
                )
            self._skip_ws()
            if self._source[self._position] == "}":  # vírgula final
                self._position += 1
                return obj

    def _array(self) -> list[_Node]:
        self._expect("[")
        arr: list[_Node] = []
        self._skip_ws()
        if self._source[self._position] == "]":
            self._position += 1
            return arr
        while True:
            self._skip_ws()
            char = self._source[self._position]
            if char == ",":  # elisão (buraco no array)
                arr.append(None)
                self._position += 1
                continue
            if char == "]":
                self._position += 1
                return arr
            arr.append(self.parse_value())
            self._skip_ws()
            separator_position = self._position
            separator = self._source[separator_position]
            self._position += 1
            if separator == "]":
                return arr
            if separator != ",":
                raise UnexpectedResponseError(
                    "estado SSR malformado: esperado ',' ou ']' "
                    f"na posição {separator_position}"
                )
            self._skip_ws()
            if self._source[self._position] == "]":  # vírgula final
                self._position += 1
                return arr

    def _string(self) -> str:
        quote = self._source[self._position]
        self._position += 1
        start = self._position
        parts: list[str] = []
        while True:
            char = self._source[self._position]
            if char == "\\":
                parts.append(self._source[start : self._position])
                self._position += 1
                parts.append(self._read_escape())
                start = self._position
            elif char == quote:
                parts.append(self._source[start : self._position])
                self._position += 1
                return "".join(parts)
            else:
                self._position += 1

    def _read_escape(self) -> str:
        """Consome a sequência de escape (após a barra invertida) e devolve o texto."""
        escape = self._source[self._position]
        self._position += 1
        if escape == "u":
            return self._decode_unicode()
        if escape == "x":
            code_point = int(self._source[self._position : self._position + 2], 16)
            self._position += 2
            return chr(code_point)
        if escape in "\r\n":  # continuação de linha: não produz caractere
            if (
                escape == "\r"
                and self._position < self._length
                and self._source[self._position] == "\n"
            ):
                self._position += 1
            return ""
        return _SIMPLE_ESC.get(escape, escape)

    def _decode_unicode(self) -> str:
        source = self._source
        if source[self._position] == "{":  # \u{1F600}
            end = source.index("}", self._position)
            code_point = int(source[self._position + 1 : end], 16)
            self._position = end + 1
            return chr(code_point)
        high_surrogate = int(source[self._position : self._position + 4], 16)
        self._position += 4
        if 0xD800 <= high_surrogate <= 0xDBFF and source[self._position : self._position + 2] == "\\u":
            low_surrogate = int(source[self._position + 2 : self._position + 6], 16)
            if 0xDC00 <= low_surrogate <= 0xDFFF:  # par surrogate
                self._position += 6
                return chr(0x10000 + ((high_surrogate - 0xD800) << 10) + (low_surrogate - 0xDC00))
        return chr(high_surrogate)

    def _number(self) -> _Node:
        start = self._position
        is_negative = self._source[self._position] == "-"
        if is_negative:
            self._position += 1
        if self._source[self._position : self._position + 8] == "Infinity":
            self._position += 8
            return float("-inf") if is_negative else float("inf")
        while self._position < self._length and self._source[self._position] in _NUMBER_CHARS:
            self._position += 1
        token = self._source[start : self._position]
        lowered = token.lower()
        if lowered.startswith(("0x", "-0x")):
            return int(token, 16)
        if "." in token or "e" in lowered:
            return float(token)
        return int(token)

    def _ident(self) -> _Node:
        start = self._position
        while self._position < self._length and self._source[self._position] in _IDENT:
            self._position += 1
        name = self._source[start : self._position]
        if not name:
            raise UnexpectedResponseError(
                f"estado SSR malformado: valor inesperado na posição {start}"
            )
        if name == "void":  # `void 0` -> undefined -> None
            self._skip_ws()
            self._number()
            return None
        if name in _KEYWORDS:
            return _KEYWORDS[name]
        return _Ref(name)


def _resolve(node: _Node, env: dict[str, JsonValue]) -> JsonValue:
    if isinstance(node, _Ref):
        return env.get(node.name)
    if isinstance(node, dict):
        return {key: _resolve(value, env) for key, value in node.items()}
    if isinstance(node, list):
        return [_resolve(item, env) for item in node]
    return node


def extract_nuxt_expression(html: str) -> str:
    """Extrai a expressão JS de ``window.__NUXT__`` do HTML SSR.

    Raises:
        UnexpectedResponseError: se o marcador não for encontrado no HTML.
    """
    match = _NUXT_RE.search(html)
    if not match:
        raise UnexpectedResponseError(
            "estado __NUXT__ não encontrado no HTML do perfil "
            "(página pode ter mudado ou o perfil não existe)"
        )
    return match.group("expr").strip()


def evaluate_nuxt(expr: str) -> JsonValue:
    """Avalia a expressão ``window.__NUXT__`` (IIFE ou objeto puro) em dados Python.

    Raises:
        UnexpectedResponseError: se a expressão estiver truncada ou malformada.
    """
    try:
        return _JsLiteralParser(expr).parse_expression()
    except (IndexError, ValueError) as exc:
        raise UnexpectedResponseError(f"estado SSR malformado: {exc}") from exc


@dataclass(frozen=True)
class FeedsData:
    """``feedsData`` do estado SSR: postagens cruas e cursor da próxima página."""

    feeds: list[JsonValue]
    cursor: str | None = None


def _find_feeds_data(node: JsonValue, depth: int = 0) -> FeedsData | None:
    if node is None or depth > _MAX_FEEDS_DEPTH:
        return None
    if isinstance(node, dict):
        found = _feeds_data_of(node)
        if found is not None:
            return found
        return _search_children(node.values(), depth)
    if isinstance(node, list):
        return _search_children(node, depth)
    return None


def _search_children(children: Iterable[JsonValue], depth: int) -> FeedsData | None:
    for child in children:
        found = _find_feeds_data(child, depth + 1)
        if found is not None:
            return found
    return None


def _feeds_data_of(node: dict[str, JsonValue]) -> FeedsData | None:
    feeds_data = node.get("feedsData")
    if not isinstance(feeds_data, dict):
        return None
    feeds = feeds_data.get("feeds")
    if not isinstance(feeds, list):
        return None
    cursor = feeds_data.get("cursor")
    if not isinstance(cursor, str):
        cursor = None
    return FeedsData(feeds=feeds, cursor=cursor)


def evaluate_feeds_data(html: str) -> FeedsData:
    """Avalia o estado SSR e retorna o ``feedsData`` do perfil.

    Args:
        html: HTML da página do perfil.

    Returns:
        ``FeedsData`` com as postagens (``feeds``) e, quando presente, o
        ``cursor`` da próxima página. Retorna ``FeedsData(feeds=[])`` se não
        houver postagens.

    Raises:
        UnexpectedResponseError: se o estado SSR não for encontrado ou for inválido.
    """
    expr = extract_nuxt_expression(html)
    data = evaluate_nuxt(expr)
    feeds_data = _find_feeds_data(data)
    if feeds_data is None:
        logger.warning("nenhum feedsData encontrado no estado SSR do perfil")
        return FeedsData(feeds=[])
    return feeds_data

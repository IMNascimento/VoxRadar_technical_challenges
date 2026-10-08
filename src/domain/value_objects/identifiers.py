"""Value objects de identificação: handle, id de usuário, de postagem e de comentário."""

from __future__ import annotations

from dataclasses import dataclass

from ..exceptions import InvalidInputError, KwaiCollectorError


@dataclass(frozen=True)
class Handle:
    """Handle de usuário do Kwai, sem ``@`` e sem espaços nas bordas."""

    value: str

    def __post_init__(self) -> None:
        has_edge_space = self.value != self.value.strip()
        has_forbidden_char = any(char in self.value for char in "@ /")
        if not self.value or has_edge_space or has_forbidden_char:
            raise InvalidInputError(f"usuário inválido: {self.value!r}")


@dataclass(frozen=True)
class PhotoId:
    """Id numérico de uma postagem do Kwai."""

    value: str

    def __post_init__(self) -> None:
        if not self.value.isdigit():
            raise InvalidInputError(f"id de postagem inválido: {self.value!r}")


@dataclass(frozen=True)
class CommentId:
    """Id de um comentário do Kwai (raiz ou resposta).

    O id vem da API, então a invariante aqui é só ser não vazio e sem espaços
    nas bordas — não se exige formato numérico.
    """

    value: str

    def __post_init__(self) -> None:
        if not self.value or self.value != self.value.strip():
            raise KwaiCollectorError(f"id de comentário inválido: {self.value!r}")


@dataclass(frozen=True)
class UserId:
    """Id numérico de um usuário do Kwai, exigido pelo feed de perfil.

    Vem da API (resolução do handle), então a invariante aqui é o formato
    numérico — um handle não serve como ``user_id``.
    """

    value: str

    def __post_init__(self) -> None:
        if not self.value.isdigit():
            raise KwaiCollectorError(f"id de usuário inválido: {self.value!r}")

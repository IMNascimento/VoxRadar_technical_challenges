"""A1_Radar."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

ROOT_COMMENTS_ENDPOINT = "/rest/o/comment/list/v2"
SUB_COMMENTS_ENDPOINT = "/rest/o/comment/sublist"

END_CURSORS = {
    "",
    "no_more",
    "more_cursor_total",
}


def is_end_cursor(
    cursor: str | None,
) -> bool:
    """
    Verifica se o cursor representa
    o fim da paginação.
    """

    if cursor is None:
        return True

    normalized = str(cursor).strip().lower()

    return normalized in END_CURSORS


def get_root_comments(
    data: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Extrai os comentários raiz
    de uma resposta.
    """

    comments = data.get("rootComments")

    if not isinstance(
        comments,
        list,
    ):
        return []

    return [
        item
        for item in comments
        if isinstance(
            item,
            dict,
        )
    ]


def get_subcomments(
    data: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Extrai os subcomentários
    de uma resposta.
    """

    comments = data.get("subComments")

    if not isinstance(
        comments,
        list,
    ):
        return []

    return [
        item
        for item in comments
        if isinstance(
            item,
            dict,
        )
    ]


def get_pcursor(
    data: dict[str, Any],
) -> str | None:
    """
    Retorna o pcursor presente
    na resposta.
    """

    cursor = data.get("pcursor")

    if cursor is None:
        return None

    return str(cursor)


def build_root_payload(
    photo_id: str,
    user_id: str,
    *,
    llsid: str = "",
    pcursor: str = "",
    count: int = 10,
    selected_root_comment_id: str = "",
) -> dict[str, str]:
    """
    Monta o payload para comentários raiz.

    Regras do count:

        3  -> 10
        10 -> 10
        20 -> 20
        25 -> 25

    O builder garante apenas o mínimo de 10.
    """

    page_size = max(
        10,
        int(count),
    )

    payload: dict[str, str] = {
        "photoId": str(photo_id),
        "user_id": str(user_id),
        "order": "desc",
        "count": str(page_size),
        "photoPageType": "0",
        "requestType": "3",
        "llsid": str(llsid),
        "isPreload": "false",
        "preloadSource": "",
    }

    if pcursor:
        payload["pcursor"] = str(pcursor)

    if selected_root_comment_id:
        payload["selectedRootCommentId"] = str(selected_root_comment_id)

    return payload


def build_subcomment_payload(
    photo_id: str,
    user_id: str,
    root_comment_id: str,
    *,
    pcursor: str = "",
    count: int = 3,
    repeat_comment_ids: list[str] | None = None,
) -> dict[str, str]:
    """
    Monta o payload para subcomentários.

    A quantidade padrão é 3.

    Na primeira página o pcursor
    não é incluído.

    repeatCommentIds sempre existe,
    mesmo quando não há comentários
    repetidos.
    """

    payload: dict[str, str] = {
        "photoId": str(photo_id),
        "user_id": str(user_id),
        "rootCommentId": str(root_comment_id),
        "count": str(
            max(
                1,
                int(count),
            )
        ),
        "repeatCommentIds": "",
    }

    if pcursor:
        payload["pcursor"] = str(pcursor)

    if repeat_comment_ids:
        payload["repeatCommentIds"] = ",".join(
            str(comment_id) for comment_id in repeat_comment_ids
        )

    return payload


def get_comment_id(
    comment: dict[str, Any],
) -> str | None:
    """
    Obtém o identificador de um comentário.

    Aceita os formatos usados
    pelas respostas e pelos mocks.
    """

    for key in (
        "commentId",
        "comment_id",
        "id",
    ):
        value = comment.get(key)

        if value is None:
            continue

        identifier = str(value).strip()

        if identifier:
            return identifier

    return None


def _comment_identifier(
    comment: dict[str, Any],
) -> str:
    """
    Gera uma chave interna utilizada
    para deduplicação.
    """

    comment_id = get_comment_id(comment)

    if comment_id is not None:
        return comment_id

    return repr(comment)


def collect_root_pages(
    pages: Iterable[dict[str, Any]],
    *,
    max_comments: int | None = None,
) -> list[dict[str, Any]]:
    """
    Consolida páginas de comentários raiz.

    - remove duplicados;
    - respeita max_comments;
    - encerra em cursor final;
    - encerra em cursor repetido;
    - evita loop com páginas vazias.
    """

    collected: list[dict[str, Any]] = []

    seen_ids: set[str] = set()
    seen_cursors: set[str] = set()

    for page in pages:
        if not isinstance(
            page,
            dict,
        ):
            continue

        comments = get_root_comments(page)

        new_comments = 0

        for comment in comments:
            identifier = _comment_identifier(comment)

            if identifier in seen_ids:
                continue

            seen_ids.add(identifier)

            collected.append(comment)

            new_comments += 1

            if max_comments is not None and len(collected) >= max_comments:
                return collected[:max_comments]

        next_cursor = get_pcursor(page)

        if is_end_cursor(next_cursor):
            break

        if next_cursor is None:
            break

        if next_cursor in seen_cursors:
            break

        if not comments and new_comments == 0:
            break

        seen_cursors.add(next_cursor)

    if max_comments is not None:
        return collected[:max_comments]

    return collected


def collect_subcomment_pages(
    pages: Iterable[dict[str, Any]],
    *,
    embedded: Iterable[dict[str, Any]] | None = None,
    max_subcomments: int | None = None,
) -> list[dict[str, Any]]:
    """
    Consolida páginas de subcomentários.

    `embedded` representa subcomentários
    que já vieram junto ao comentário raiz.

    Eles são adicionados primeiro e também
    participam da deduplicação.
    """

    collected: list[dict[str, Any]] = []

    seen_ids: set[str] = set()
    seen_cursors: set[str] = set()

    if embedded is not None:
        for comment in embedded:
            if not isinstance(
                comment,
                dict,
            ):
                continue

            identifier = _comment_identifier(comment)

            if identifier in seen_ids:
                continue

            seen_ids.add(identifier)

            collected.append(comment)

            if max_subcomments is not None and len(collected) >= max_subcomments:
                return collected[:max_subcomments]

    for page in pages:
        if not isinstance(
            page,
            dict,
        ):
            continue

        comments = get_subcomments(page)

        new_comments = 0

        for comment in comments:
            identifier = _comment_identifier(comment)

            if identifier in seen_ids:
                continue

            seen_ids.add(identifier)

            collected.append(comment)

            new_comments += 1

            if max_subcomments is not None and len(collected) >= max_subcomments:
                return collected[:max_subcomments]

        next_cursor = get_pcursor(page)

        if is_end_cursor(next_cursor):
            break

        if next_cursor is None:
            break

        if next_cursor in seen_cursors:
            break

        if not comments and new_comments == 0:
            break

        seen_cursors.add(next_cursor)

    if max_subcomments is not None:
        return collected[:max_subcomments]

    return collected

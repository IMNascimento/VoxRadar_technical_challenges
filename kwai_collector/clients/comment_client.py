from time import sleep
from typing import Any

import httpx

from kwai_collector.config import settings

A1_Radar = "A1_Radar"

BASE_URL = "https://www.kwai.com"

ROOT_COMMENTS_ENDPOINT = "/rest/o/w/pc/getComments/list"
SUB_COMMENTS_ENDPOINT = "/rest/o/w/pc/getSubComments/list"

DEFAULT_TIMEOUT = 20.0


DEFAULT_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": ("pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7"),
    "Content-Type": "application/json",
    "Origin": "https://www.kwai.com",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/152.0.0.0 Safari/537.36"
    ),
}


class KwaiCommentsError(RuntimeError):
    pass


# ============================================================
# CLIENT WEB / PC
# ============================================================


def create_client(
    cookies: dict[str, str] | None = None,
    cookie_header: str | None = None,
) -> httpx.Client:
    headers = dict(DEFAULT_HEADERS)

    effective_cookie = cookie_header if cookie_header is not None else settings.cookie

    if cookies is None and effective_cookie:
        headers["Cookie"] = effective_cookie

    return httpx.Client(
        base_url=BASE_URL,
        headers=headers,
        cookies=cookies,
        timeout=DEFAULT_TIMEOUT,
        follow_redirects=True,
    )


def _post(
    endpoint: str,
    payload: dict[str, Any],
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    owns_client = client is None

    if client is None:
        client = create_client()

    try:
        response = client.post(
            endpoint,
            json=payload,
        )

        response.raise_for_status()

        data = response.json()

        if not isinstance(
            data,
            dict,
        ):
            raise KwaiCommentsError("A resposta do Kwai não é um objeto JSON.")

        return data

    except httpx.HTTPStatusError as exc:
        raise KwaiCommentsError(
            f"Erro HTTP {exc.response.status_code} ao acessar {endpoint}"
        ) from exc

    except httpx.RequestError as exc:
        raise KwaiCommentsError(f"Erro de conexão com o Kwai: {exc}") from exc

    except ValueError as exc:
        raise KwaiCommentsError("O Kwai retornou uma resposta que não é JSON.") from exc

    finally:
        if owns_client:
            client.close()


# ============================================================
# COMENTÁRIOS WEB
# ============================================================


def get_comments(
    photo_id: str,
    cursor: str = "",
    root_comment_count: int = 10,
    sub_comment_count: int = 2,
    *,
    client: httpx.Client | None = None,
) -> tuple[list[dict[str, Any]], str]:
    payload = {
        "photo_id": str(photo_id),
        "cursor": cursor,
        "rootCommentCount": (root_comment_count),
        "subCommentCount": (sub_comment_count),
    }

    data = _post(
        ROOT_COMMENTS_ENDPOINT,
        payload,
        client=client,
    )

    result = data.get("result")

    if result != 1:
        raise KwaiCommentsError(
            "A API de comentários retornou erro. "
            f"result={result!r} "
            f"error_msg="
            f"{data.get('error_msg')!r}"
        )

    if "host-name" in data and "rootComments" not in data:
        raise KwaiCommentsError(
            "O Kwai respondeu com result=1, "
            "mas não enviou 'rootComments'. "
            "A sessão atual pode não ter "
            "permissão para acessar a lista "
            "completa de comentários."
        )

    comments_raw = data.get("rootComments")

    if not isinstance(
        comments_raw,
        list,
    ):
        comments: list[dict[str, Any]] = []

    else:
        comments = [
            dict(item)
            for item in comments_raw
            if isinstance(
                item,
                dict,
            )
        ]

    next_cursor = data.get("cursor")

    if next_cursor in (
        None,
        "",
    ):
        next_cursor = "no_more"

    return (
        comments,
        str(next_cursor),
    )


def get_subcomments(
    photo_id: str,
    root_comment_id: str,
    cursor: str = "",
    sub_comment_count: int | None = None,
    *,
    client: httpx.Client | None = None,
) -> tuple[list[dict[str, Any]], str]:
    if sub_comment_count is None:
        sub_comment_count = 3 if cursor else 5

    payload = {
        "photo_id": str(photo_id),
        "cursor": cursor,
        "rootCommentId": str(root_comment_id),
        "subCommentCount": (sub_comment_count),
    }

    data = _post(
        SUB_COMMENTS_ENDPOINT,
        payload,
        client=client,
    )

    result = data.get("result")

    if result != 1:
        raise KwaiCommentsError(
            "A API de respostas retornou erro. "
            f"result={result!r} "
            f"error_msg="
            f"{data.get('error_msg')!r}"
        )

    subcomments_raw = data.get("subComments")

    if not isinstance(
        subcomments_raw,
        list,
    ):
        subcomments: list[dict[str, Any]] = []

    else:
        subcomments = [
            dict(item)
            for item in subcomments_raw
            if isinstance(
                item,
                dict,
            )
        ]

    next_cursor = data.get("cursor")

    if next_cursor in (
        None,
        "",
    ):
        next_cursor = "no_more"

    return (
        subcomments,
        str(next_cursor),
    )


def get_all_comments(
    photo_id: str,
    *,
    max_comments: int | None = None,
    delay: float = 0.25,
    client: httpx.Client | None = None,
) -> list[dict[str, Any]]:
    owns_client = client is None

    if client is None:
        client = create_client()

    comments: list[dict[str, Any]] = []

    seen_ids: set[str] = set()

    cursor = ""
    first_page = True

    try:
        while cursor != "no_more":
            root_comment_count = 10 if first_page else 20

            (
                page_comments,
                next_cursor,
            ) = get_comments(
                photo_id=photo_id,
                cursor=cursor,
                root_comment_count=(root_comment_count),
                sub_comment_count=2,
                client=client,
            )

            new_comments = 0

            for comment in page_comments:
                comment_id = comment.get("commentId")

                if comment_id is None:
                    comment_id = comment.get("comment_id")

                identifier = (
                    str(comment_id) if comment_id is not None else repr(comment)
                )

                if identifier in seen_ids:
                    continue

                seen_ids.add(identifier)

                comments.append(comment)

                new_comments += 1

                if max_comments is not None and len(comments) >= max_comments:
                    return comments[:max_comments]

            if next_cursor == "no_more":
                break

            if next_cursor == cursor:
                break

            if not page_comments and new_comments == 0:
                break

            cursor = next_cursor

            first_page = False

            if delay > 0:
                sleep(delay)

        return comments

    finally:
        if owns_client:
            client.close()


def get_all_subcomments(
    photo_id: str,
    root_comment: dict[str, Any],
    *,
    max_subcomments: int | None = None,
    delay: float = 0.25,
    client: httpx.Client | None = None,
) -> list[dict[str, Any]]:
    root_comment_id = root_comment.get("commentId")

    if root_comment_id is None:
        root_comment_id = root_comment.get("comment_id")

    if root_comment_id is None:
        raise KwaiCommentsError("O comentário principal não possui commentId.")

    owns_client = client is None

    if client is None:
        client = create_client()

    collected: list[dict[str, Any]] = []

    seen_ids: set[str] = set()

    embedded = root_comment.get(
        "subComments",
        [],
    )

    if isinstance(
        embedded,
        list,
    ):
        for subcomment in embedded:
            if not isinstance(
                subcomment,
                dict,
            ):
                continue

            sub_id = subcomment.get("commentId")

            if sub_id is None:
                sub_id = subcomment.get("comment_id")

            identifier = str(sub_id) if sub_id is not None else repr(subcomment)

            if identifier in seen_ids:
                continue

            seen_ids.add(identifier)

            collected.append(dict(subcomment))

            if max_subcomments is not None and len(collected) >= max_subcomments:
                return collected[:max_subcomments]

    total_raw = root_comment.get("subCommentCount")

    try:
        total = int(total_raw) if total_raw is not None else None

    except (
        TypeError,
        ValueError,
    ):
        total = None

    if total is not None and total <= len(collected):
        return collected

    cursor = ""

    try:
        while cursor != "no_more":
            (
                page,
                next_cursor,
            ) = get_subcomments(
                photo_id=photo_id,
                root_comment_id=str(root_comment_id),
                cursor=cursor,
                client=client,
            )

            new_items = 0

            for subcomment in page:
                sub_id = subcomment.get("commentId")

                if sub_id is None:
                    sub_id = subcomment.get("comment_id")

                identifier = str(sub_id) if sub_id is not None else repr(subcomment)

                if identifier in seen_ids:
                    continue

                seen_ids.add(identifier)

                collected.append(subcomment)

                new_items += 1

                if max_subcomments is not None and len(collected) >= max_subcomments:
                    return collected[:max_subcomments]

            if total is not None and len(collected) >= total:
                break

            if next_cursor == "no_more":
                break

            if next_cursor == cursor:
                break

            if not page and new_items == 0:
                break

            cursor = next_cursor

            if delay > 0:
                sleep(delay)

        return collected

    finally:
        if owns_client:
            client.close()


def get_all_comments_with_replies(
    photo_id: str,
    *,
    max_comments: int | None = None,
    max_subcomments_per_comment: (int | None) = None,
    delay: float = 0.25,
) -> list[dict[str, Any]]:
    with create_client() as client:
        root_comments = get_all_comments(
            photo_id=photo_id,
            max_comments=(max_comments),
            delay=delay,
            client=client,
        )

        complete_comments: list[dict[str, Any]] = []

        for root_comment in root_comments:
            result = dict(root_comment)

            total_raw = root_comment.get(
                "subCommentCount",
                0,
            )

            try:
                total_subcomments = int(total_raw or 0)

            except (
                TypeError,
                ValueError,
            ):
                total_subcomments = 0

            if total_subcomments > 0:
                subcomments = get_all_subcomments(
                    photo_id=(photo_id),
                    root_comment=(root_comment),
                    max_subcomments=(max_subcomments_per_comment),
                    delay=delay,
                    client=client,
                )

                result["subComments"] = subcomments

            complete_comments.append(result)

        return complete_comments

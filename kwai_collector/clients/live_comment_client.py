"""A1_Radar."""

from __future__ import annotations

import logging
import math
import random
import re
from collections.abc import Callable
from time import monotonic, sleep
from typing import Any

import httpx

from kwai_collector.clients.comment_collection_progress import (
    CommentCollectionInterrupted,
    CommentCollectionProgress,
)
from kwai_collector.clients.mobile_comment_client import (
    build_root_payload,
    get_pcursor,
    get_root_comments,
    is_end_cursor,
)
from kwai_collector.clients.request_rate_limiter import (
    RequestRateLimiter,
    parse_retry_after,
    sleep_in_chunks,
)
from kwai_collector.security.signature_provider import (
    MobileRequestProvider,
)

logger = logging.getLogger(__name__)


class LiveCommentClient:
    # 501 is retried only for this endpoint: it has been observed after
    # successful pages, and the limited attempts do not assume its cause.
    _RETRY_STATUSES = frozenset({429, 500, 501, 502, 503, 504})

    def __init__(
        self,
        auth_provider: MobileRequestProvider | None = None,
        *,
        client: httpx.Client | None = None,
        base_url: str = "https://api2-us.kwaipros.com",
        max_attempts: int = 3,
        backoff_base: float = 1.0,
        page_delay: float = 1.0,
    ) -> None:
        if type(max_attempts) is not int or max_attempts < 1:
            raise ValueError("max_attempts deve ser um inteiro positivo.")
        for name, value in (("backoff_base", backoff_base), ("page_delay", page_delay)):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value < 0
            ):
                raise ValueError(f"{name} deve ser um número finito não negativo.")
        self.auth_provider = auth_provider
        self.client = client or httpx.Client(http2=True, timeout=30.0)
        self.base_url = base_url.rstrip("/")
        self.max_attempts = max_attempts
        self.backoff_base = float(backoff_base)
        self.page_delay = float(page_delay)
        self.rate_limiter = RequestRateLimiter(
            self.page_delay,
            clock=lambda: monotonic(),
            sleeper=lambda delay: sleep(delay),
        )

    @staticmethod
    def _unique_comments(
        comments: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        seen: set[str] = set()
        for comment in comments:
            identifier = next(
                (
                    str(comment[field])
                    for field in ("commentId", "comment_id", "id")
                    if comment.get(field) not in (None, "")
                ),
                None,
            )
            if identifier is not None:
                if identifier in seen:
                    continue
                seen.add(identifier)
            output.append(dict(comment))
        return output

    def _request_page(
        self,
        *,
        query: dict[str, str],
        payload: dict[str, str],
        headers: dict[str, str],
        progress: CommentCollectionProgress,
        debug: bool,
    ) -> dict[str, Any]:
        assert self.auth_provider is not None
        url = f"{self.base_url}/rest/o/comment/list/v2"
        for attempt in range(1, self.max_attempts + 1):
            retry_after: float | None = None
            self.rate_limiter.wait_before_request()
            try:
                # The profile refreshes its timestamp here, and each signer
                # receives the unsigned page again, including the same cursor.
                prepared = self.auth_provider.prepare(
                    query=dict(query), body=dict(payload), headers=dict(headers)
                )
            except (ValueError, TypeError, RuntimeError) as exc:
                raise CommentCollectionInterrupted(
                    "Falha ao preparar a requisição de comentários "
                    f"({type(exc).__name__}).",
                    progress,
                ) from exc

            try:
                self.rate_limiter.mark_request()
                response = self.client.post(
                    url,
                    params=prepared.query,
                    data=prepared.body,
                    headers=prepared.headers,
                )
            except httpx.RequestError as exc:
                if attempt == self.max_attempts:
                    raise CommentCollectionInterrupted(
                        "Falha de rede ao coletar comentários "
                        f"({type(exc).__name__}, {attempt} tentativas).",
                        progress,
                    ) from exc
                reason = type(exc).__name__
            else:
                if debug:
                    logger.debug(
                        "HTTP status da API de comentários: %d.", response.status_code
                    )
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    status = response.status_code
                    retry_after = parse_retry_after(response.headers.get("Retry-After"))
                    if retry_after is not None:
                        self.rate_limiter.defer_for(retry_after)
                    if (
                        status not in self._RETRY_STATUSES
                        or attempt == self.max_attempts
                    ):
                        raise CommentCollectionInterrupted(
                            "A API de comentários retornou "
                            f"HTTP {status} após {attempt} tentativa(s).",
                            progress,
                        ) from exc
                    reason = f"HTTP {status}"
                else:
                    try:
                        data = response.json()
                    except ValueError as exc:
                        raise CommentCollectionInterrupted(
                            "A API mobile retornou uma resposta que não é JSON.",
                            progress,
                        ) from exc
                    if not isinstance(data, dict):
                        raise CommentCollectionInterrupted(
                            "A resposta da API mobile não possui o formato esperado.",
                            progress,
                        )
                    if data.get("error_msg") or (
                        "result" in data and data.get("result") != 1
                    ):
                        # Never echo arbitrary error text supplied by the API.
                        raise CommentCollectionInterrupted(
                            "A API mobile rejeitou a requisição de comentários.",
                            progress,
                        )
                    return data

            delay = min(self.backoff_base * (2 ** (attempt - 1)), 60.0)
            delay = max(delay, retry_after or 0.0)
            logger.warning(
                "Falha na página de comentários (%s); nova tentativa %d/%d em %.1f s.",
                reason,
                attempt + 1,
                self.max_attempts,
                delay,
            )
            sleep_in_chunks(delay, lambda wait: sleep(wait))
        raise AssertionError("O limite de tentativas deve encerrar a requisição.")

    def fetch_root_comments(
        self,
        photo_id: str,
        user_id: str,
        max_comments: int | None = 20,
        *,
        debug: bool = False,
        resume: CommentCollectionProgress | None = None,
        on_progress: Callable[[CommentCollectionProgress], None] | None = None,
    ) -> list[dict[str, Any]]:
        """Collect root comments, preserving validated pages if collection stops.

        ``max_comments=None`` follows cursors until the server reports the end.
        A saved progress snapshot resumes from the first page not yet collected.
        """
        if resume is not None and (
            resume.photo_id != photo_id or resume.user_id != user_id
        ):
            raise ValueError("O progresso salvo pertence a outro post ou autor.")
        if max_comments is not None and max_comments <= 0:
            return []
        all_comments = self._unique_comments(resume.comments) if resume else []
        pcursor = resume.pcursor if resume else ""
        llsid = (
            resume.llsid
            if resume
            else str(random.randint(1000000000000000000, 9999999999999999999))
        )

        def snapshot(*, complete: bool = False) -> CommentCollectionProgress:
            return CommentCollectionProgress(
                photo_id=photo_id,
                user_id=user_id,
                llsid=llsid,
                pcursor=pcursor,
                comments=[dict(comment) for comment in all_comments],
                complete=complete,
            )

        if (max_comments is not None and len(all_comments) >= max_comments) or (
            resume is not None and resume.complete and is_end_cursor(pcursor)
        ):
            if on_progress is not None:
                on_progress(snapshot(complete=True))
            return all_comments if max_comments is None else all_comments[:max_comments]
        if self.auth_provider is None:
            raise CommentCollectionInterrupted(
                "O fluxo mobile requer um provedor de autenticação suportado.",
                snapshot(),
            )

        seen_cursors = {pcursor}
        while max_comments is None or len(all_comments) < max_comments:
            count = (
                20
                if max_comments is None
                else min(20, max_comments - len(all_comments))
            )
            payload = build_root_payload(
                photo_id=photo_id,
                user_id=user_id,
                llsid=llsid,
                pcursor=pcursor,
                count=count,
            )
            data = self._request_page(
                query={"llsid": llsid},
                payload=payload,
                headers={"Accept": "application/json"},
                progress=snapshot(),
                debug=debug,
            )
            comments = get_root_comments(data)
            all_comments = self._unique_comments(all_comments + comments)
            next_cursor = get_pcursor(data)
            complete = is_end_cursor(next_cursor) or (
                max_comments is not None and len(all_comments) >= max_comments
            )
            repeated_cursor = not complete and next_cursor in seen_cursors
            pcursor = next_cursor or ""
            progress = snapshot(complete=complete)
            if on_progress is not None:
                on_progress(progress)
            logger.info(
                "Página de comentários recebida: %d comentários; total único: %d.",
                len(comments),
                len(all_comments),
            )
            if debug:
                logger.debug(
                    "Página mobile: %d comentários; total único: %d.",
                    len(comments),
                    len(all_comments),
                )
            if complete:
                break
            if repeated_cursor:
                raise CommentCollectionInterrupted(
                    "A API mobile repetiu um cursor sem informar o fim da coleta.",
                    progress,
                )
            seen_cursors.add(pcursor)

        return all_comments if max_comments is None else all_comments[:max_comments]


def extract_ids_from_url(
    url: str,
) -> tuple[str, str] | None:
    match = re.search(
        r"/photo/(\d+)/(\d+)(?:[/?#]|$)",
        url,
    )

    if match:
        return (
            match.group(2),
            match.group(1),
        )

    match = re.search(
        r"@([^/]+)/video/(\d+)",
        url,
    )

    if match:
        return (
            match.group(2),
            match.group(1),
        )

    match = re.search(
        r"/video/(\d+)",
        url,
    )

    if match:
        photo_id = match.group(1)

        user_match = re.search(
            r"@([^/]+)",
            url,
        )

        user_id = user_match.group(1) if user_match else "unknown"

        return (
            photo_id,
            user_id,
        )

    return None

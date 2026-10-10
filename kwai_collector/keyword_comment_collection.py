"""Collect main comments for the posts returned by a keyword search.

A1_Radar.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final
from urllib.parse import quote

import httpx

from kwai_collector.clients.comment_collection_progress import (
    CommentCollectionInterrupted,
)
from kwai_collector.parsers.comment_parser import parse_comment
from kwai_collector.providers.mobile_comment_provider import MobileCommentProvider
from kwai_collector.security.signature_provider import MobileRequestProvider

logger = logging.getLogger(__name__)

KWAI_BASE_URL: Final = "https://www.kwai.com"

PostRaw = dict[str, Any]
CommentJson = dict[str, Any]
CommentRecord = dict[str, Any]
ProgressCallback = Callable[[dict[str, Any]], None]


@dataclass(slots=True)
class KeywordCommentCollector:
    auth_provider: MobileRequestProvider
    output_dir: Path
    request_interval: float
    max_attempts: int = 3
    backoff_base: float = 1.0
    on_progress: ProgressCallback | None = None

    def collect(
        self,
        posts: list[PostRaw],
        *,
        keyword: str,
        max_comments: int | None,
    ) -> dict[str, Any]:
        selected_posts = self._deduplicate_posts(posts)
        self.output_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        provider = self._create_provider()
        records: list[CommentRecord] = []

        result = self._create_result(
            keyword=keyword,
            max_comments=max_comments,
            records=records,
        )

        self._persist_result(
            result,
            records,
            total_posts=len(selected_posts),
        )

        try:
            self._collect_posts(
                selected_posts,
                provider=provider,
                records=records,
                result=result,
                max_comments=max_comments,
            )
        finally:
            self._close_provider(provider)

        logger.info(
            "Busca com comentários: %d posts; %d comentários; %d posts com erro.",
            result["total_posts_processados"],
            result["total_comentarios_coletados"],
            result["total_posts_com_erro"],
        )

        return result

    def _collect_posts(
        self,
        posts: list[PostRaw],
        *,
        provider: MobileCommentProvider,
        records: list[CommentRecord],
        result: dict[str, Any],
        max_comments: int | None,
    ) -> None:
        total_posts = len(posts)

        for index, post in enumerate(
            posts,
            start=1,
        ):
            record, checkpoint_path = self._collect_post(
                post,
                provider=provider,
                index=index,
                total_posts=total_posts,
                max_comments=max_comments,
            )

            records.append(record)

            self._persist_result(
                result,
                records,
                total_posts=total_posts,
            )

            if checkpoint_path is not None and "erro" not in record:
                checkpoint_path.unlink(
                    missing_ok=True,
                )

    def _collect_post(
        self,
        post: PostRaw,
        *,
        provider: MobileCommentProvider,
        index: int,
        total_posts: int,
        max_comments: int | None,
    ) -> tuple[CommentRecord, Path | None]:
        photo_id = self._extract_photo_id(post)

        if photo_id is None:
            return (
                self._invalid_post_record(post),
                None,
            )

        user_id = self._extract_user_id(post)
        url = self._build_post_url(
            post,
            photo_id,
        )
        target = url or photo_id

        checkpoint_path = self.output_dir / f"{photo_id}_comentarios.coleta.json"

        provider.checkpoint_path = checkpoint_path

        logger.info(
            "[%d/%d] Coletando comentários do post %s.",
            index,
            total_posts,
            photo_id,
        )

        comments, error = self._fetch_comments(
            provider,
            target=target,
            user_id=user_id,
            max_comments=max_comments,
        )

        record = self._build_record(
            post,
            photo_id=photo_id,
            url=url,
            comments=comments,
            error=error,
        )

        self._save_individual_comments(
            photo_id,
            comments,
        )

        return record, checkpoint_path

    def _fetch_comments(
        self,
        provider: MobileCommentProvider,
        *,
        target: str,
        user_id: str | None,
        max_comments: int | None,
    ) -> tuple[list[CommentJson], str | None]:
        try:
            models = provider.get_comments(
                target,
                max_comments=max_comments,
                user_id=user_id,
            )

            comments = [
                dict(
                    model.model_dump(
                        mode="json",
                    )
                )
                for model in models
            ]

            return comments, None

        except CommentCollectionInterrupted as exc:
            comments = [
                dict(
                    parse_comment(
                        comment,
                        target,
                    ).model_dump(
                        mode="json",
                    )
                )
                for comment in exc.progress.comments
            ]

            return comments, str(exc)

        except (
            ValueError,
            TypeError,
            RuntimeError,
            httpx.HTTPError,
        ) as exc:
            error = f"Falha na coleta de comentários ({type(exc).__name__})."

            return [], error

    def _build_record(
        self,
        post: PostRaw,
        *,
        photo_id: str,
        url: str | None,
        comments: list[CommentJson],
        error: str | None,
    ) -> CommentRecord:
        record: CommentRecord = {
            "photo_id": photo_id,
            "url": url,
            "caption": post.get("caption"),
            "quantidade": len(comments),
            "comentarios": comments,
        }

        if error is None:
            return record

        record["erro"] = error

        logger.warning(
            "Coleta incompleta do post %s: %s %d comentários preservados.",
            photo_id,
            error,
            len(comments),
        )

        return record

    def _save_individual_comments(
        self,
        photo_id: str,
        comments: list[CommentJson],
    ) -> None:
        output_path = self.output_dir / f"{photo_id}_comentarios.json"

        if not comments and output_path.exists():
            return

        output_path.write_text(
            json.dumps(
                comments,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def _create_provider(
        self,
    ) -> MobileCommentProvider:
        provider = MobileCommentProvider(
            auth_provider=self.auth_provider,
        )

        provider.max_attempts = self.max_attempts
        provider.backoff_base = self.backoff_base
        provider.page_delay = self.request_interval

        return provider

    def _persist_result(
        self,
        result: dict[str, Any],
        records: list[CommentRecord],
        *,
        total_posts: int,
    ) -> None:
        result.update(
            total_posts_processados=len(records),
            total_comentarios_coletados=sum(
                int(record["quantidade"]) for record in records
            ),
            total_posts_com_erro=sum("erro" in record for record in records),
            complete=(
                len(records) == total_posts
                and all("erro" not in record for record in records)
            ),
        )

        if self.on_progress is not None:
            self.on_progress(result)

    @staticmethod
    def _create_result(
        *,
        keyword: str,
        max_comments: int | None,
        records: list[CommentRecord],
    ) -> dict[str, Any]:
        return {
            "palavra_chave": keyword,
            "coletado_em": datetime.now(UTC).isoformat(),
            "limite_comentarios_por_post": max_comments,
            "total_posts_processados": 0,
            "total_comentarios_coletados": 0,
            "total_posts_com_erro": 0,
            "complete": False,
            "posts": records,
        }

    @staticmethod
    def _deduplicate_posts(
        posts: list[PostRaw],
    ) -> list[PostRaw]:
        selected: list[PostRaw] = []
        seen_ids: set[str] = set()

        for post in posts:
            identifier = str(post.get("photo_id_str") or "")

            if identifier and identifier in seen_ids:
                continue

            seen_ids.add(identifier)
            selected.append(post)

        return selected

    @staticmethod
    def _extract_photo_id(
        post: PostRaw,
    ) -> str | None:
        photo_id = str(post.get("photo_id_str") or "")

        if not photo_id.isdigit():
            return None

        return photo_id

    @staticmethod
    def _extract_user_id(
        post: PostRaw,
    ) -> str | None:
        user_id = post.get("user_id_str")

        if user_id is None:
            return None

        return str(user_id)

    @staticmethod
    def _build_post_url(
        post: PostRaw,
        photo_id: str,
    ) -> str | None:
        handle = str(post.get("kwai_id") or "").strip().removeprefix("@")

        if not handle:
            return None

        encoded_handle = quote(
            handle,
            safe="",
        )

        return f"{KWAI_BASE_URL}/@{encoded_handle}/video/{photo_id}"

    @staticmethod
    def _invalid_post_record(
        post: PostRaw,
    ) -> CommentRecord:
        return {
            "photo_id": str(post.get("photo_id_str") or ""),
            "url": None,
            "caption": post.get("caption"),
            "quantidade": 0,
            "comentarios": [],
            "erro": ("A busca retornou uma postagem sem ID numérico válido."),
        }

    @staticmethod
    def _close_provider(
        provider: MobileCommentProvider,
    ) -> None:
        if provider.live_client is None:
            return

        provider.live_client.client.close()


def collect_keyword_comments(
    posts: list[PostRaw],
    *,
    keyword: str,
    max_comments: int | None,
    output_dir: Path,
    request_interval: float,
    auth_provider: MobileRequestProvider,
    max_attempts: int = 3,
    backoff_base: float = 1.0,
    on_progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    collector = KeywordCommentCollector(
        auth_provider=auth_provider,
        output_dir=output_dir,
        request_interval=request_interval,
        max_attempts=max_attempts,
        backoff_base=backoff_base,
        on_progress=on_progress,
    )

    return collector.collect(
        posts,
        keyword=keyword,
        max_comments=max_comments,
    )

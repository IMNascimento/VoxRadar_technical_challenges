"""A1_Radar."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast

import httpx

from kwai_collector.clients.comment_client import KwaiCommentsError
from kwai_collector.clients.comment_collection_progress import (
    CommentCollectionInterrupted,
)
from kwai_collector.providers.mobile_comment_provider import (
    MobileCommentProvider,
)

JsonObject = dict[str, object]
RawComment = dict[str, Any]

ExtractPhotoIdFn = Callable[[str], str]
GetTinyCommentsFn = Callable[..., list[RawComment]]
BuildTinyQueryParamsFn = Callable[[], dict[str, str]]
SaveJsonFn = Callable[[object, Path], None]
SaveCheckpointFn = Callable[[Any, Path], None]


class ParsedComment(Protocol):
    def model_dump(
        self,
        *,
        mode: str,
    ) -> dict[str, Any]: ...


ParseCommentFn = Callable[
    [RawComment, str],
    ParsedComment,
]

CreateMobileProviderFn = Callable[
    ...,
    MobileCommentProvider,
]


@dataclass(
    frozen=True,
    slots=True,
)
class CommentCommandDependencies:
    extract_photo_id: ExtractPhotoIdFn
    get_tiny_comments: GetTinyCommentsFn
    build_tiny_query_params: BuildTinyQueryParamsFn
    parse_comment: ParseCommentFn
    create_mobile_provider: CreateMobileProviderFn
    save_json: SaveJsonFn
    save_checkpoint: SaveCheckpointFn


@dataclass(
    frozen=True,
    slots=True,
)
class CommentCommandOptions:
    post_url: str
    output_dir: Path
    max_comments: int | None
    user_id: str | None
    resume: bool
    request_interval: float
    debug: bool


@dataclass(
    frozen=True,
    slots=True,
)
class CommentCollectionResult:
    exit_code: int
    comments: list[JsonObject]


@dataclass(
    frozen=True,
    slots=True,
)
class CommentCommand:
    dependencies: CommentCommandDependencies
    logger: logging.Logger
    mobile_threshold: int = 20

    def execute(
        self,
        options: CommentCommandOptions,
    ) -> int:
        photo_id = self._extract_photo_id(options.post_url)

        if photo_id is None:
            return 1

        result = self._collect(
            photo_id,
            options,
        )

        if result.exit_code != 0:
            return result.exit_code

        output_path = options.output_dir / f"{photo_id}_comentarios.json"

        self.dependencies.save_json(
            result.comments,
            output_path,
        )

        self._checkpoint_path(
            options.output_dir,
            photo_id,
        ).unlink(missing_ok=True)

        self.logger.info(
            "Comentários coletados: %d",
            len(result.comments),
        )

        self.logger.info(
            "Resultado salvo em: %s",
            output_path,
        )

        return 0

    def _extract_photo_id(
        self,
        post_url: str,
    ) -> str | None:
        try:
            return self.dependencies.extract_photo_id(post_url)
        except ValueError as exc:
            self.logger.error(
                "%s",
                exc,
            )
            return None

    def _collect(
        self,
        photo_id: str,
        options: CommentCommandOptions,
    ) -> CommentCollectionResult:
        if self._uses_mobile(options):
            return self._collect_mobile(
                photo_id,
                options,
            )

        return self._collect_tiny(
            photo_id,
            options,
        )

    def _uses_mobile(
        self,
        options: CommentCommandOptions,
    ) -> bool:
        return (
            options.resume
            or options.max_comments is None
            or options.max_comments > self.mobile_threshold
        )

    def _collect_mobile(
        self,
        photo_id: str,
        options: CommentCommandOptions,
    ) -> CommentCollectionResult:
        checkpoint_path = self._checkpoint_path(
            options.output_dir,
            photo_id,
        )

        try:
            provider = self.dependencies.create_mobile_provider(
                request_interval=(options.request_interval),
                checkpoint_path=(checkpoint_path),
                resume=options.resume,
            )

            comments = provider.get_comments(
                options.post_url,
                max_comments=(options.max_comments),
                user_id=options.user_id,
            )

        except CommentCollectionInterrupted as exc:
            return self._handle_interrupted_collection(
                exc,
                photo_id=photo_id,
                options=options,
                checkpoint_path=(checkpoint_path),
            )

        except (
            ValueError,
            TypeError,
            RuntimeError,
            httpx.HTTPError,
        ) as exc:
            self.logger.error(
                "Falha ao coletar comentários pelo fluxo mobile: %s",
                exc,
            )

            return CommentCollectionResult(
                exit_code=1,
                comments=[],
            )

        normalized = [dict(comment.model_dump(mode="json")) for comment in comments]

        return CommentCollectionResult(
            exit_code=0,
            comments=normalized,
        )

    def _handle_interrupted_collection(
        self,
        exc: CommentCollectionInterrupted,
        *,
        photo_id: str,
        options: CommentCommandOptions,
        checkpoint_path: Path,
    ) -> CommentCollectionResult:
        self.dependencies.save_checkpoint(
            exc.progress,
            checkpoint_path,
        )

        normalized = self._normalize_partial_comments(
            exc.progress.comments,
            options.post_url,
        )

        partial_path = options.output_dir / f"{photo_id}_comentarios.json"

        if normalized or not partial_path.exists():
            self.dependencies.save_json(
                normalized,
                partial_path,
            )

        self.logger.error(
            "Coleta incompleta: %s "
            "%d comentários salvos em %s. "
            "Repita o comando com "
            "--resume para retomar.",
            exc,
            len(normalized),
            partial_path,
        )

        return CommentCollectionResult(
            exit_code=1,
            comments=normalized,
        )

    def _normalize_partial_comments(
        self,
        comments: list[RawComment],
        post_url: str,
    ) -> list[JsonObject]:
        return [
            dict(
                self.dependencies.parse_comment(
                    comment,
                    post_url,
                ).model_dump(mode="json")
            )
            for comment in comments
        ]

    def _collect_tiny(
        self,
        photo_id: str,
        options: CommentCommandOptions,
    ) -> CommentCollectionResult:
        limit = cast(
            int,
            options.max_comments,
        )

        try:
            comments = self.dependencies.get_tiny_comments(
                photo_id=photo_id,
                query_params=(self.dependencies.build_tiny_query_params()),
                debug=options.debug,
            )

        except KwaiCommentsError as exc:
            self.logger.error(
                "Falha ao coletar comentários: %s",
                exc,
            )

            return CommentCollectionResult(
                exit_code=1,
                comments=[],
            )

        normalized = self._normalize_tiny_comments(
            comments[:limit],
            options.post_url,
        )

        return CommentCollectionResult(
            exit_code=0,
            comments=normalized,
        )

    def _normalize_tiny_comments(
        self,
        comments: list[RawComment],
        post_url: str,
    ) -> list[JsonObject]:
        normalized: list[JsonObject] = []

        for comment in comments:
            parsed = self._parse_tiny_comment(
                comment,
                post_url,
            )

            if parsed is not None:
                normalized.append(parsed)

        return normalized

    def _parse_tiny_comment(
        self,
        comment: RawComment,
        post_url: str,
    ) -> JsonObject | None:
        try:
            parsed = self.dependencies.parse_comment(
                comment,
                post_url,
            )

        except ValueError as exc:
            self.logger.warning(
                "Comentário ignorado: %s",
                exc,
            )
            return None

        return dict(parsed.model_dump(mode="json"))

    @staticmethod
    def _checkpoint_path(
        output_dir: Path,
        photo_id: str,
    ) -> Path:
        return output_dir / (f"{photo_id}_comentarios.coleta.json")

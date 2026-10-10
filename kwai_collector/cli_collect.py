"""A1_Radar."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from time import sleep
from typing import Any, cast

import httpx

from kwai_collector.cli_builders import (
    montar_perfil,
    montar_post_fallback,
    montar_url_post,
)
from kwai_collector.cli_utils import (
    limpar_usuario,
    nome_arquivo_seguro,
    salvar_json,
)
from kwai_collector.clients.comment_client import KwaiCommentsError
from kwai_collector.clients.comment_collection_progress import (
    CommentCollectionInterrupted,
)
from kwai_collector.clients.post_detail_client import KwaiPostError
from kwai_collector.providers.mobile_comment_provider import (
    MobileCommentProvider,
)

PostRaw = dict[str, Any]
JsonObject = dict[str, object]

GetProfilePostsFn = Callable[..., list[PostRaw]]
GetPostDetailsFn = Callable[..., JsonObject]
GetTinyCommentsFn = Callable[..., list[PostRaw]]

CreateMobileProviderFn = Callable[
    [float],
    MobileCommentProvider,
]

BuildTinyQueryParamsFn = Callable[
    [],
    dict[str, str],
]

ParseCommentFn = Callable[
    [dict[str, Any], str],
    Any,
]


@dataclass(
    frozen=True,
    slots=True,
)
class AggregateCollectionDependencies:
    get_profile_posts: GetProfilePostsFn
    get_post_details: GetPostDetailsFn
    get_tiny_comments: GetTinyCommentsFn
    create_mobile_provider: CreateMobileProviderFn
    build_tiny_query_params: BuildTinyQueryParamsFn
    parse_comment: ParseCommentFn


@dataclass(
    frozen=True,
    slots=True,
)
class AggregateCollectionOptions:
    profile: str
    output_dir: Path
    delay: float
    debug: bool
    max_posts: int
    max_comments: int | None
    request_interval: float


@dataclass(
    slots=True,
)
class AggregateCollectionState:
    posts: list[JsonObject] = field(
        default_factory=list,
    )
    comments_by_post: list[JsonObject] = field(
        default_factory=list,
    )
    total_comments: int = 0

    def add_comments_record(
        self,
        record: JsonObject,
    ) -> None:
        self.comments_by_post.append(record)

        quantidade = record.get(
            "quantidade",
            0,
        )

        if isinstance(
            quantidade,
            int,
        ):
            self.total_comments += quantidade


@dataclass(
    frozen=True,
    slots=True,
)
class CommentCollectionResult:
    comments: list[JsonObject]
    error: str | None = None


@dataclass(
    frozen=True,
    slots=True,
)
class AggregateCollectionCommand:
    dependencies: AggregateCollectionDependencies
    logger: logging.Logger
    mobile_threshold: int = 20

    def execute(
        self,
        options: AggregateCollectionOptions,
    ) -> int:
        usuario = self._clean_user(options.profile)

        if usuario is None:
            return 1

        posts = self._fetch_posts(
            usuario,
            options.max_posts,
        )

        if posts is None:
            return 1

        try:
            mobile_provider = self._prepare_mobile_provider(options)
        except (
            ValueError,
            TypeError,
            RuntimeError,
        ) as exc:
            self.logger.error(
                "Falha ao preparar o fluxo mobile de comentários: %s",
                exc,
            )
            return 1

        state = AggregateCollectionState()

        perfil = montar_perfil(
            usuario,
            posts,
        )

        total = len(posts)

        for indice, post in enumerate(
            posts,
            start=1,
        ):
            self._process_post(
                post,
                indice=indice,
                total=total,
                state=state,
                options=options,
                mobile_provider=mobile_provider,
            )

            self._wait_between_posts(
                indice,
                total,
                options.delay,
            )

        self._save_documents(
            usuario=usuario,
            perfil=perfil,
            state=state,
            options=options,
        )

        self.logger.info(
            "Posts coletados: %d",
            len(state.posts),
        )

        self.logger.info(
            "Comentários coletados: %d",
            state.total_comments,
        )

        return 0

    def _clean_user(
        self,
        profile: str,
    ) -> str | None:
        try:
            return limpar_usuario(profile)

        except ValueError as exc:
            self.logger.error(
                "%s",
                exc,
            )
            return None

    def _fetch_posts(
        self,
        user: str,
        max_posts: int,
    ) -> list[PostRaw] | None:
        query_user = f"@{user}"

        self.logger.info(
            "Perfil solicitado: %s",
            query_user,
        )

        try:
            posts = self.dependencies.get_profile_posts(
                user_id=query_user,
                max_paginas=1,
                delay=0.0,
            )

        except (
            httpx.RequestError,
            httpx.HTTPStatusError,
            RuntimeError,
        ) as exc:
            self.logger.error(
                "Falha ao coletar o perfil: %s",
                exc,
            )
            return None

        if posts:
            return posts[:max_posts]

        self.logger.error(
            "Nenhuma postagem encontrada para o perfil %s.",
            query_user,
        )

        return None

    def _prepare_mobile_provider(
        self,
        options: AggregateCollectionOptions,
    ) -> MobileCommentProvider | None:
        if not self._uses_mobile(options.max_comments):
            return None

        return self.dependencies.create_mobile_provider(options.request_interval)

    def _uses_mobile(
        self,
        max_comments: int | None,
    ) -> bool:
        return max_comments is None or max_comments > self.mobile_threshold

    def _process_post(
        self,
        post: PostRaw,
        *,
        indice: int,
        total: int,
        state: AggregateCollectionState,
        options: AggregateCollectionOptions,
        mobile_provider: MobileCommentProvider | None,
    ) -> None:
        photo_id_raw = post.get("photo_id_str")

        if photo_id_raw is None:
            self.logger.warning(
                "[%d/%d] Post sem photo_id.",
                indice,
                total,
            )
            return

        photo_id = str(photo_id_raw)

        url_post = montar_url_post(post)

        post_details = self._fetch_post_details(
            post,
            photo_id=photo_id,
            url_post=url_post,
            indice=indice,
            total=total,
        )

        state.posts.append(post_details)

        result = self._collect_comments(
            post,
            photo_id=photo_id,
            url_post=url_post,
            indice=indice,
            total=total,
            options=options,
            mobile_provider=mobile_provider,
        )

        record = self._build_comments_record(
            post,
            photo_id=photo_id,
            url_post=url_post,
            result=result,
        )

        state.add_comments_record(record)

    def _fetch_post_details(
        self,
        post: PostRaw,
        *,
        photo_id: str,
        url_post: str | None,
        indice: int,
        total: int,
    ) -> JsonObject:
        fallback = montar_post_fallback(post)

        if url_post is None:
            return fallback

        try:
            return self.dependencies.get_post_details(
                url_post,
                expected_photo_id=photo_id,
            )

        except KwaiPostError as exc:
            self.logger.warning(
                "[%d/%d] Falha ao obter detalhes do post %s: %s",
                indice,
                total,
                photo_id,
                exc,
            )

            fallback["erro_detalhes"] = str(exc)

            return fallback

    def _collect_comments(
        self,
        post: PostRaw,
        *,
        photo_id: str,
        url_post: str | None,
        indice: int,
        total: int,
        options: AggregateCollectionOptions,
        mobile_provider: MobileCommentProvider | None,
    ) -> CommentCollectionResult:
        try:
            comments = self._fetch_comments(
                post,
                photo_id=photo_id,
                url_post=url_post,
                options=options,
                mobile_provider=mobile_provider,
            )

            self._warn_if_below_limit(
                quantidade=len(comments),
                max_comments=(options.max_comments),
                photo_id=photo_id,
                indice=indice,
                total=total,
            )

            return CommentCollectionResult(comments=comments)

        except CommentCollectionInterrupted as exc:
            comments = [
                dict(
                    self.dependencies.parse_comment(
                        comment,
                        url_post or photo_id,
                    ).model_dump(mode="json")
                )
                for comment in exc.progress.comments
            ]

            self.logger.warning(
                "[%d/%d] Coleta incompleta "
                "do post %s: %s "
                "%d comentários preservados; "
                "retome com o comando "
                "comentarios e --resume.",
                indice,
                total,
                photo_id,
                exc,
                len(comments),
            )

            return CommentCollectionResult(
                comments=comments,
                error=str(exc),
            )

        except (
            KwaiCommentsError,
            ValueError,
            TypeError,
            RuntimeError,
            httpx.HTTPError,
        ) as exc:
            self.logger.warning(
                "[%d/%d] Falha ao coletar comentários do post %s: %s",
                indice,
                total,
                photo_id,
                exc,
            )

            return CommentCollectionResult(
                comments=[],
                error=str(exc),
            )

    def _fetch_comments(
        self,
        post: PostRaw,
        *,
        photo_id: str,
        url_post: str | None,
        options: AggregateCollectionOptions,
        mobile_provider: MobileCommentProvider | None,
    ) -> list[JsonObject]:
        if mobile_provider is None:
            return self._fetch_tiny_comments(
                photo_id=photo_id,
                max_comments=cast(
                    int,
                    options.max_comments,
                ),
                debug=options.debug,
            )

        return self._fetch_mobile_comments(
            mobile_provider,
            post=post,
            photo_id=photo_id,
            url_post=url_post,
            max_comments=(options.max_comments),
            output_dir=(options.output_dir),
        )

    def _fetch_tiny_comments(
        self,
        *,
        photo_id: str,
        max_comments: int,
        debug: bool,
    ) -> list[JsonObject]:
        comments = self.dependencies.get_tiny_comments(
            photo_id=photo_id,
            query_params=(self.dependencies.build_tiny_query_params()),
            debug=debug,
        )

        return [dict(comment) for comment in comments[:max_comments]]

    def _fetch_mobile_comments(
        self,
        provider: MobileCommentProvider,
        *,
        post: PostRaw,
        photo_id: str,
        url_post: str | None,
        max_comments: int | None,
        output_dir: Path,
    ) -> list[JsonObject]:
        provider.checkpoint_path = output_dir / (f"{photo_id}_comentarios.coleta.json")

        user_id_raw = post.get("user_id_str")

        user_id = str(user_id_raw) if user_id_raw is not None else None

        target = url_post or photo_id

        comments = provider.get_comments(
            target,
            max_comments=max_comments,
            user_id=user_id,
        )

        return [dict(comment.model_dump(mode="json")) for comment in comments]

    def _warn_if_below_limit(
        self,
        *,
        quantidade: int,
        max_comments: int | None,
        photo_id: str,
        indice: int,
        total: int,
    ) -> None:
        if max_comments is None or quantidade >= max_comments:
            return

        self.logger.warning(
            "[%d/%d] Quantidade menor "
            "que a solicitada para "
            "o post %s. "
            "Solicitado: %d. "
            "Obtido: %d.",
            indice,
            total,
            photo_id,
            max_comments,
            quantidade,
        )

    @staticmethod
    def _build_comments_record(
        post: PostRaw,
        *,
        photo_id: str,
        url_post: str | None,
        result: CommentCollectionResult,
    ) -> JsonObject:
        record: JsonObject = {
            "photo_id": photo_id,
            "url": url_post,
            "caption": post.get("caption"),
            "quantidade": len(result.comments),
            "comentarios": (result.comments),
        }

        if result.error is not None:
            record["erro"] = result.error

        return record

    @staticmethod
    def _wait_between_posts(
        indice: int,
        total: int,
        delay: float,
    ) -> None:
        if indice < total and delay > 0:
            sleep(delay)

    def _save_documents(
        self,
        *,
        usuario: str,
        perfil: JsonObject,
        state: AggregateCollectionState,
        options: AggregateCollectionOptions,
    ) -> None:
        collected_at = datetime.now(UTC).isoformat()

        safe_name = nome_arquivo_seguro(usuario)

        posts_path = options.output_dir / f"{safe_name}_posts.json"

        comments_path = options.output_dir / (f"{safe_name}_comentarios.json")

        posts_document = {
            "perfil": perfil,
            "coletado_em": collected_at,
            "limite_posts": (options.max_posts),
            "total_posts_coletados": (len(state.posts)),
            "posts": state.posts,
        }

        comments_document = {
            "perfil": perfil,
            "coletado_em": collected_at,
            "limite_posts": (options.max_posts),
            "limite_comentarios_por_post": (options.max_comments),
            "total_posts_processados": (len(state.comments_by_post)),
            "total_comentarios_coletados": (state.total_comments),
            "posts": (state.comments_by_post),
        }

        salvar_json(
            posts_document,
            posts_path,
        )

        salvar_json(
            comments_document,
            comments_path,
        )

        self._clear_successful_checkpoints(
            state,
            options.output_dir,
        )

    @staticmethod
    def _clear_successful_checkpoints(
        state: AggregateCollectionState,
        output_dir: Path,
    ) -> None:
        for record in state.comments_by_post:
            if "erro" in record:
                continue

            checkpoint = output_dir / (f"{record['photo_id']}_comentarios.coleta.json")

            checkpoint.unlink(missing_ok=True)


def executar_coleta_agregada_com_dependencias(
    perfil_informado: str,
    output_dir: Path,
    delay: float,
    debug: bool,
    *,
    max_posts: int,
    max_comentarios_por_post: int,
    get_all_profile_posts_fn: GetProfilePostsFn,
    get_post_details_fn: GetPostDetailsFn,
    get_comments_fn: GetTinyCommentsFn,
    logger: logging.Logger,
) -> int:
    """
    Mantém compatibilidade com o contrato antigo
    enquanto a CLI utiliza AggregateCollectionCommand.
    """

    def get_comments_adapter(
        **kwargs: Any,
    ) -> list[PostRaw]:
        return get_comments_fn(
            photo_id=kwargs["photo_id"],
            max_comments=(max_comentarios_por_post),
            debug=kwargs["debug"],
        )

    def create_mobile_provider_unavailable(
        _: float,
    ) -> MobileCommentProvider:
        raise RuntimeError("Fluxo mobile não utilizado pelo adaptador legado.")

    def empty_query_params() -> dict[str, str]:
        return {}

    def parse_comment_unavailable(
        _: dict[str, Any],
        __: str,
    ) -> Any:
        raise RuntimeError("Parser não utilizado pelo adaptador legado.")

    dependencies = AggregateCollectionDependencies(
        get_profile_posts=(get_all_profile_posts_fn),
        get_post_details=(get_post_details_fn),
        get_tiny_comments=(get_comments_adapter),
        create_mobile_provider=(create_mobile_provider_unavailable),
        build_tiny_query_params=(empty_query_params),
        parse_comment=(parse_comment_unavailable),
    )

    command = AggregateCollectionCommand(
        dependencies=dependencies,
        logger=logger,
        mobile_threshold=(max_comentarios_por_post),
    )

    options = AggregateCollectionOptions(
        profile=perfil_informado,
        output_dir=output_dir,
        delay=delay,
        debug=debug,
        max_posts=max_posts,
        max_comments=(max_comentarios_por_post),
        request_interval=0.0,
    )

    return command.execute(options)

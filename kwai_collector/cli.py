"""A1_Radar."""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, Final

import httpx

from kwai_collector.cli_builders import montar_tiny_query_params
from kwai_collector.cli_collect import (
    AggregateCollectionCommand,
    AggregateCollectionDependencies,
    AggregateCollectionOptions,
)
from kwai_collector.cli_commands import (
    ProfileCommand,
    SearchCommand,
)
from kwai_collector.cli_comments import (
    CommentCommand,
    CommentCommandDependencies,
    CommentCommandOptions,
)
from kwai_collector.cli_normalizers import (
    normalizar_posts_com_parser,
)
from kwai_collector.cli_parsers import (
    criar_parser_buscar as _criar_parser_buscar,
)
from kwai_collector.cli_parsers import (
    criar_parser_coletar as _criar_parser_coletar,
)
from kwai_collector.cli_parsers import (
    criar_parser_comentarios as _criar_parser_comentarios,
)
from kwai_collector.cli_parsers import (
    criar_parser_perfil as _criar_parser_perfil,
)
from kwai_collector.cli_parsers import (
    mostrar_ajuda_principal as mostrar_ajuda,
)
from kwai_collector.cli_utils import (
    extrair_photo_id,
    limpar_usuario,
    nome_arquivo_seguro,
    salvar_json,
)
from kwai_collector.clients.kwai_client import search_all_posts
from kwai_collector.clients.post_detail_client import get_post_details
from kwai_collector.clients.profile_client import get_all_profile_posts
from kwai_collector.clients.tiny_comment_client import get_tiny_comments
from kwai_collector.config import settings
from kwai_collector.keyword_comment_collection import (
    collect_keyword_comments,
)
from kwai_collector.parsers.comment_parser import parse_comment
from kwai_collector.parsers.post_parser import parse_post
from kwai_collector.providers.comment_checkpoint import (
    save_comment_checkpoint,
)
from kwai_collector.providers.mobile_comment_provider import (
    MobileCommentProvider,
)
from kwai_collector.security.local_comment_request_provider import (
    criar_local_comment_request_provider,
)
from kwai_collector.security.mobile_request_provider_factory import (
    criar_mobile_request_provider,
)
from kwai_collector.security.signature_provider import (
    MobileRequestProvider,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)

logging.getLogger("httpx").setLevel(logging.WARNING)


MAX_POSTS: Final = 10
MAX_COMENTARIOS_POR_POST: Final = 20

PostRaw = dict[str, Any]

CommandHandler = Callable[
    [list[str]],
    int,
]


def _criar_auth_provider_mobile() -> MobileRequestProvider:
    if not settings.mobile_auth_endpoint:
        return criar_mobile_request_provider(
            delegate=criar_local_comment_request_provider(
                query_fields=settings.mobile_query_fields,
                body_fields=settings.mobile_body_fields,
                header_fields=settings.mobile_header_fields,
            ),
        )
    return criar_mobile_request_provider(
        query_fields=settings.mobile_query_fields,
        body_fields=settings.mobile_body_fields,
        header_fields=settings.mobile_header_fields,
        auth_endpoint=settings.mobile_auth_endpoint,
        auth_token=settings.mobile_auth_token,
        auth_timeout=settings.mobile_auth_timeout,
    )


def _criar_mobile_comment_provider(
    *,
    request_interval: float,
    checkpoint_path: Path | None = None,
    resume: bool = False,
) -> MobileCommentProvider:
    provider = MobileCommentProvider()

    provider.auth_provider = _criar_auth_provider_mobile()

    provider.max_attempts = settings.max_tentativas

    provider.backoff_base = settings.backoff_base

    provider.page_delay = request_interval

    provider.checkpoint_path = checkpoint_path

    provider.resume_collection = resume

    return provider


def _criar_mobile_provider_para_coleta(
    request_interval: float,
) -> MobileCommentProvider:
    return _criar_mobile_comment_provider(
        request_interval=request_interval,
    )


def _normalizar_posts(
    posts: list[PostRaw],
) -> list[dict[str, Any]]:
    return normalizar_posts_com_parser(
        posts,
        parse_post,
        logger,
    )


def _criar_comando_busca() -> SearchCommand:
    return SearchCommand(
        search_posts=search_all_posts,
        normalize_posts=_normalizar_posts,
        safe_filename=nome_arquivo_seguro,
        save_json=salvar_json,
        logger=logger,
    )


def _criar_comando_perfil() -> ProfileCommand:
    return ProfileCommand(
        clean_user=limpar_usuario,
        get_profile_posts=get_all_profile_posts,
        normalize_posts=_normalizar_posts,
        safe_filename=nome_arquivo_seguro,
        save_json=salvar_json,
        logger=logger,
    )


def _criar_comando_comentarios() -> CommentCommand:
    return CommentCommand(
        dependencies=(
            CommentCommandDependencies(
                extract_photo_id=extrair_photo_id,
                get_tiny_comments=get_tiny_comments,
                build_tiny_query_params=(montar_tiny_query_params),
                parse_comment=parse_comment,
                create_mobile_provider=(_criar_mobile_comment_provider),
                save_json=salvar_json,
                save_checkpoint=(save_comment_checkpoint),
            )
        ),
        logger=logger,
        mobile_threshold=(MAX_COMENTARIOS_POR_POST),
    )


def _criar_comando_coleta() -> AggregateCollectionCommand:
    return AggregateCollectionCommand(
        dependencies=(
            AggregateCollectionDependencies(
                get_profile_posts=(get_all_profile_posts),
                get_post_details=(get_post_details),
                get_tiny_comments=(get_tiny_comments),
                create_mobile_provider=(_criar_mobile_provider_para_coleta),
                build_tiny_query_params=(montar_tiny_query_params),
                parse_comment=parse_comment,
            )
        ),
        logger=logger,
        mobile_threshold=(MAX_COMENTARIOS_POR_POST),
    )


def _main_coletar(
    argv: list[str] | None = None,
) -> int:
    args = _criar_parser_coletar().parse_args(argv)

    options = AggregateCollectionOptions(
        profile=args.perfil,
        output_dir=args.output_dir,
        delay=args.delay,
        debug=args.debug,
        max_posts=MAX_POSTS,
        max_comments=args.max_comments,
        request_interval=(args.request_interval),
    )

    return _criar_comando_coleta().execute(options)


def _executar_busca(
    argv: list[str],
) -> int:
    args = _criar_parser_buscar().parse_args(argv)

    resultado_busca = _criar_comando_busca().run(
        keyword=args.palavra_chave,
        output_dir=args.output_dir,
        delay=args.delay,
    )

    if resultado_busca.exit_code != 0:
        return resultado_busca.exit_code

    if not args.with_comments:
        return 0

    comments_path = args.output_dir / (
        f"busca_{nome_arquivo_seguro(args.palavra_chave)}_comentarios.json"
    )

    normalized_ids = {str(post.get("id")) for post in resultado_busca.posts}

    selected_posts = [
        post
        for post in resultado_busca.raw_posts
        if str(post.get("photo_id_str")) in normalized_ids
    ]

    try:
        result = collect_keyword_comments(
            selected_posts,
            keyword=args.palavra_chave,
            max_comments=args.max_comments,
            output_dir=args.output_dir,
            request_interval=(args.request_interval),
            auth_provider=(_criar_auth_provider_mobile()),
            max_attempts=(settings.max_tentativas),
            backoff_base=(settings.backoff_base),
            on_progress=(
                lambda data: salvar_json(
                    data,
                    comments_path,
                )
            ),
        )

    except (
        ValueError,
        TypeError,
        RuntimeError,
        httpx.HTTPError,
    ) as exc:
        logger.error(
            "Falha na busca com comentários (%s).",
            type(exc).__name__,
        )

        return 1

    logger.info(
        "Comentários da busca salvos em: %s",
        comments_path,
    )

    return 1 if result["total_posts_com_erro"] else 0


def _executar_perfil(
    argv: list[str],
) -> int:
    args = _criar_parser_perfil().parse_args(argv)

    return _criar_comando_perfil().execute(
        profile=args.perfil,
        output_dir=args.output_dir,
        delay=args.delay,
    )


def _executar_comentarios(
    argv: list[str],
) -> int:
    args = _criar_parser_comentarios().parse_args(argv)

    options = CommentCommandOptions(
        post_url=args.postagem_url,
        output_dir=args.output_dir,
        max_comments=args.max_comments,
        user_id=args.user_id,
        resume=args.resume,
        request_interval=(args.request_interval),
        debug=args.debug,
    )

    return _criar_comando_comentarios().execute(options)


def _dispatch_command(
    argumentos: list[str],
) -> int:
    handlers: dict[
        str,
        CommandHandler,
    ] = {
        "buscar": _executar_busca,
        "perfil": _executar_perfil,
        "comentarios": (_executar_comentarios),
        "coletar": lambda args: _main_coletar(args),
    }

    handler = handlers.get(argumentos[0])

    if handler is None:
        return _main_coletar(argumentos)

    return handler(argumentos[1:])


def main(
    argv: list[str] | None = None,
) -> int:
    argumentos = list(argv) if argv is not None else sys.argv[1:]

    if not argumentos or argumentos[0] in {
        "-h",
        "--help",
    }:
        mostrar_ajuda()
        return 0

    return _dispatch_command(argumentos)


if __name__ == "__main__":
    raise SystemExit(main())

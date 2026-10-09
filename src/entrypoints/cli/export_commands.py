"""Comandos da CLI (``search``, ``profile`` e ``comments``) que coletam e exportam JSON.

Cada comando valida a entrada antes de abrir rede (exit ``2`` se inválida), cria
um diretório de execução e grava cada resultado assim que ele chega; sai com
exit ``1`` se alguma etapa falhar ou não puder ser gravada. As docstrings dos
comandos ficam em inglês porque viram o texto do ``--help``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Annotated, TypeVar

import typer
from pydantic import ValidationError

from ...application.dtos.collection_result import CollectionResult
from ...application.dtos.commands import (
    CommentCollectionCommand,
    CommentVersions,
    ProfileCollectionCommand,
    SearchCommand,
)
from ...config.settings import Settings
from ...domain.entities.comment import Comment
from ...domain.entities.post import Post
from ...domain.enums.post_sort_by import PostSortBy
from ...domain.exceptions.domain_exceptions import InvalidInputError, KwaiCollectorError
from ...domain.value_objects.post_reference import PostReference
from ...infrastructure.container.container import Services, build_services
from ...shared.logging.logging_config import get_logger, setup_logging
from .export_files import create_export_directory, write_export

app = typer.Typer(rich_markup_mode=None)
logger = get_logger("cli")

OutDirectoryOption = Annotated[
    Path,
    typer.Option("--out", "-o", help="Base output directory (default: exports)."),
]
VerboseOption = Annotated[bool, typer.Option("--verbose", "-v", help="Enable DEBUG logs.")]
OptionalLimitOption = Annotated[
    int | None,
    typer.Option("--limit", "-l", min=1, help="Maximum items; default: all."),
]
RepliesOption = Annotated[
    bool,
    typer.Option("--with-comments-replies", help="Export root comments and replies together."),
]
SortOption = Annotated[
    PostSortBy | None,
    typer.Option(
        "--sort-by",
        help="Order collected posts highest first; unknown counts last. Applied after --limit.",
    ),
]

Results = Iterable[CollectionResult[Post | Comment]]
CommandT = TypeVar("CommandT")


def _source(result: CollectionResult[Post | Comment]) -> str:
    if result.post is not None:
        return result.post.url
    return "posts" if result.kind == "posts" else "unknown post"


def _save_result(run: Path, result: CollectionResult[Post | Comment]) -> bool:
    """Grava o resultado e indica se a etapa terminou sem falha de coleta ou de escrita."""
    if result.error is not None:
        logger.error("collection failed (%s, %s): %s", result.stage, _source(result), result.error)
    try:
        write_export(run, result)
    except OSError as exc:
        logger.error("export failed (%s, %s): %s", result.kind, _source(result), exc)
        return False
    return result.error is None


def _build_command(build: Callable[[], CommandT]) -> CommandT:
    """Monta o comando, validando a entrada antes de criar diretórios ou abrir sessões HTTP.

    Raises:
        typer.Exit: com código ``2`` se a entrada for inválida.
    """
    try:
        return build()
    except InvalidInputError as exc:
        logger.error("invalid input: %s", exc)
        raise typer.Exit(code=2) from exc


def _run_exports(owner: str, produce: Callable[[Services], Results], out: Path) -> None:
    """Executa a coleta e grava cada resultado no diretório de execução.

    Todos os resultados são gravados antes de sair. Termina com exit ``1`` se
    algum falhou ou não pôde ser gravado, ou se a configuração, a coleta ou o
    encerramento dos serviços lançarem erro de coleta, de validação ou de I/O.

    Raises:
        typer.Exit: com código ``1`` em qualquer dessas falhas.
    """
    has_failed = False
    try:
        settings = Settings()
        run = create_export_directory(out, owner)
        typer.echo(f"Export directory: {run}")
        with build_services(settings) as services:
            for result in produce(services):
                if not _save_result(run, result):
                    has_failed = True
    except (KwaiCollectorError, ValidationError, OSError) as exc:
        logger.error("collection/export/close failed: %s", exc)
        raise typer.Exit(code=1) from exc
    if has_failed:
        raise typer.Exit(code=1)


def _owner_from_post(post: PostReference) -> str:
    """Extrai o dono da postagem da URL; sem ele, usa ``post-<id>``."""
    return post.owner or f"post-{post.photo_id.value}"


@app.command("search")
def search_posts(
    keyword: Annotated[
        list[str], typer.Option("--keyword", "-k", help="Keyword; repeat for multiple.")
    ],
    limit: Annotated[
        int, typer.Option("--limit", "-l", min=1, help="Maximum unique posts in total.")
    ] = 20,
    out: OutDirectoryOption = Path("exports"),
    verbose: VerboseOption = False,
    sort_by: SortOption = None,
) -> None:
    """Search posts by keywords and export posts.json (no cursor pagination)."""
    setup_logging(verbose=verbose)
    command = _build_command(lambda: SearchCommand.create(keyword, limit=limit, sort_by=sort_by))
    _run_exports("search", lambda services: [services.search_posts.execute(command)], out)


@app.command("profile")
def collect_profile(
    user: Annotated[str, typer.Option("--user", "-u", help="Profile handle, with or without @.")],
    limit: OptionalLimitOption = None,
    with_comments: Annotated[
        bool, typer.Option("--with-comments", help="Export root comments only.")
    ] = False,
    with_comments_replies: RepliesOption = False,
    comments_limit: Annotated[
        int | None,
        typer.Option(
            "--comments-limit",
            min=1,
            help="Maximum raw root comments per post; replies do not count.",
        ),
    ] = None,
    out: OutDirectoryOption = Path("exports"),
    verbose: VerboseOption = False,
    sort_by: SortOption = None,
) -> None:
    """Export profile posts and optionally comments for each post."""
    setup_logging(verbose=verbose)
    command = _build_command(
        lambda: ProfileCollectionCommand.create(
            user,
            limit=limit,
            comments_limit=comments_limit,
            comment_versions=CommentVersions.from_flags(
                roots=with_comments, replies=with_comments_replies
            ),
            sort_by=sort_by,
        )
    )
    _run_exports(
        command.handle.value, lambda services: services.profile_bundle.execute(command), out
    )


@app.command("comments")
def collect_comments(
    url: Annotated[
        str, typer.Option("--url", help="Post URL containing /video/<id> or /photo/<id>.")
    ],
    limit: OptionalLimitOption = None,
    with_comments_replies: RepliesOption = False,
    out: OutDirectoryOption = Path("exports"),
    verbose: VerboseOption = False,
) -> None:
    """Export comments from one post; --limit counts raw roots, not replies."""
    setup_logging(verbose=verbose)
    command = _build_command(
        lambda: CommentCollectionCommand.create(
            url,
            limit=limit,
            versions=CommentVersions.REPLIES if with_comments_replies else CommentVersions.ROOTS,
        )
    )
    _run_exports(
        _owner_from_post(command.post),
        lambda services: services.comment_versions.execute(command),
        out,
    )

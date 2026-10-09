"""Comandos ingleses com exportação JSON organizada por diretório."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from pathlib import Path
from typing import Annotated
from urllib.parse import unquote, urlsplit

import typer
from pydantic import ValidationError

from ..application.collect_profile_bundle import ProfileCollectionOptions
from ..application.collection_result import CollectionResult
from ..application.exceptions import CollectionInterruptedError
from ..application.post_ordering import PostSortBy
from ..config import Settings
from ..container import Services, build_services
from ..domain.exceptions import InvalidInputError, KwaiCollectorError
from ..domain.identity import extract_photo_id, normalize_handle
from ..shared.logging_config import get_logger, setup_logging
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


def _save_result(run: Path, result: CollectionResult) -> bool:
    if result.error is not None:
        logger.error(
            "collection failed (%s, %s): %s", result.stage, result.post_url or "posts", result.error
        )
    try:
        write_export(run, result)
    except OSError as exc:
        logger.error("export failed (%s, %s): %s", result.kind, result.post_url or "posts", exc)
        return False
    return result.error is None


def _run_exports(
    owner: str,
    produce: Callable[[Services], Iterable[CollectionResult]],
    out: Path,
) -> None:
    has_failed = False
    try:
        settings = Settings()
        run = create_export_directory(out, owner)
        typer.echo(f"Export directory: {run}")
        with build_services(settings) as services:
            for result in produce(services):
                if not _save_result(run, result):
                    has_failed = True
    except InvalidInputError as exc:
        logger.error("invalid input: %s", exc)
        raise typer.Exit(code=2) from exc
    except (KwaiCollectorError, ValidationError, OSError) as exc:
        logger.error("collection/export/close failed: %s", exc)
        raise typer.Exit(code=1) from exc
    if has_failed:
        raise typer.Exit(code=1)


def _search_results(
    services: Services, keywords: list[str], limit: int, sort_by: PostSortBy | None
) -> Iterator[CollectionResult]:
    try:
        posts = services.search_posts.execute(keywords, limit=limit, sort_by=sort_by)
    except KwaiCollectorError as exc:
        partial = exc.partial if isinstance(exc, CollectionInterruptedError) else ()
        yield CollectionResult("posts", partial, "posts", error=exc)
        return
    yield CollectionResult("posts", tuple(posts), "posts")


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
    _run_exports("search", lambda services: _search_results(services, keyword, limit, sort_by), out)


def _profile_results(
    services: Services,
    user: str,
    options: ProfileCollectionOptions,
) -> Iterator[CollectionResult]:
    return services.profile_bundle.execute(user, options)


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
    try:
        handle = normalize_handle(user)
    except InvalidInputError as exc:
        logger.error("invalid input: %s", exc)
        raise typer.Exit(code=2) from exc
    options = ProfileCollectionOptions(
        limit=limit,
        comments_limit=comments_limit,
        with_comments=with_comments,
        with_replies=with_comments_replies,
        sort_by=sort_by,
    )
    _run_exports(
        handle.value, lambda services: _profile_results(services, handle.value, options), out
    )


def _comment_results(
    services: Services,
    url: str,
    options: ProfileCollectionOptions,
) -> Iterator[CollectionResult]:
    return services.comment_versions.execute(
        url,
        limit=options.comments_limit,
        with_comments=options.with_comments,
        with_replies=options.with_replies,
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
    try:
        photo_id = extract_photo_id(url)
    except InvalidInputError as exc:
        logger.error("invalid input: %s", exc)
        raise typer.Exit(code=2) from exc
    owner = next(
        (
            unquote(part[1:])
            for part in urlsplit(url).path.split("/")
            if part.startswith("@") and len(part) > 1
        ),
        f"post-{photo_id.value}",
    )
    options = ProfileCollectionOptions(
        comments_limit=limit,
        with_comments=not with_comments_replies,
        with_replies=with_comments_replies,
    )
    _run_exports(owner, lambda services: _comment_results(services, url, options), out)

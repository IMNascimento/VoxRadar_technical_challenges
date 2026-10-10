import json
import logging
from collections.abc import Callable, Sequence
from pathlib import Path

import typer
from pydantic import BaseModel

from kwai_collector import scraper
from kwai_collector.client import KwaiError

log = logging.getLogger("kwai")

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Coleta posts e comentários públicos do Kwai e salva em JSON.",
)


def setup_logging(verbose: bool) -> None:
    # logs ficam no stderr para não misturar com o JSON da saída
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )
    if not verbose:
        logging.getLogger("httpx").setLevel(logging.WARNING)


def collect_and_save(collect: Callable[[], Sequence[BaseModel]], out: Path | None) -> None:
    try:
        items = collect()
    except scraper.InvalidInput as e:
        log.error("entrada inválida: %s", e)
        raise typer.Exit(code=2) from e
    except KwaiError as e:
        log.error("erro na coleta: %s", e)
        raise typer.Exit(code=1) from e

    text = json.dumps([item.model_dump() for item in items], ensure_ascii=False, indent=2)
    if out is None:
        typer.echo(text)
        return
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
    except OSError as e:
        log.error("não foi possível salvar %s: %s", out, e)
        raise typer.Exit(code=1) from e
    log.info("%d itens salvos em %s", len(items), out)


@app.command()
def search(
    keyword: list[str] = typer.Option(..., "--keyword", "-k", help="Palavra-chave (pode repetir)."),
    limit: int = typer.Option(20, "--limit", "-l", min=1, help="Máximo de posts."),
    out: Path | None = typer.Option(None, "--out", "-o", help="Arquivo JSON de saída."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Mostra logs de debug."),
) -> None:
    """Busca posts por palavra-chave."""
    setup_logging(verbose)
    collect_and_save(lambda: scraper.search_posts(keyword, limit), out)


@app.command()
def profile(
    user: str = typer.Option(..., "--user", "-u", help="Usuário, com ou sem @."),
    limit: int | None = typer.Option(None, "--limit", "-l", min=1, help="Máximo de posts."),
    out: Path | None = typer.Option(None, "--out", "-o", help="Arquivo JSON de saída."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Mostra logs de debug."),
) -> None:
    """Coleta os posts de um usuário."""
    setup_logging(verbose)
    collect_and_save(lambda: scraper.get_user_posts(user, limit), out)


@app.command()
def comments(
    url: str = typer.Option(..., "--url", help="Link do post (.../video/<id>)."),
    limit: int | None = typer.Option(
        None, "--limit", "-l", min=1, help="Máximo de comentários (respostas não contam)."
    ),
    with_replies: bool = typer.Option(False, "--with-replies", help="Inclui as respostas."),
    out: Path | None = typer.Option(None, "--out", "-o", help="Arquivo JSON de saída."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Mostra logs de debug."),
) -> None:
    """Coleta os comentários de um post."""
    setup_logging(verbose)
    collect_and_save(lambda: scraper.get_comments(url, limit, with_replies), out)

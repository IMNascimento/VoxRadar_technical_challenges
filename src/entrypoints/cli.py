"""Interface de linha de comando do coletor (Typer)."""

from __future__ import annotations

import typer

from .export_commands import app as export_app

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Collect public Kwai posts and comments; export JSON to organized directories.",
    rich_markup_mode=None,
)
app.add_typer(export_app)

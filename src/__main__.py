"""Ponto de entrada: ``python -m src`` e script ``kwai-collector``."""

from __future__ import annotations

from .entrypoints.cli.app import app

if __name__ == "__main__":
    app()

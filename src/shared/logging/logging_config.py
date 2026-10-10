"""Configuração central de logging: formato, nível e loggers no namespace ``src``."""

from __future__ import annotations

import logging

# Nome do logger do coletor: aparece no output e é contrato observável.
COLLECTOR_LOGGER_NAME: str = "collector"


def setup_logging(*, verbose: bool = False) -> None:
    """Configura o logging da aplicação de forma idempotente.

    Args:
        verbose: Se ``True``, usa nível ``DEBUG``; caso contrário, ``INFO``.
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    logging.getLogger("src").setLevel(level)


def get_logger(name: str) -> logging.Logger:
    """Retorna um logger no namespace ``src``."""
    return logging.getLogger(f"src.{name}")

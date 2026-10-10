"""A1_Radar."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Final

from kwai_collector.cli_utils import (
    limite_comentarios,
    numero_nao_negativo,
)
from kwai_collector.config import settings

DEFAULT_OUTPUT_DIR: Final = Path("samples")
DEFAULT_MAX_COMMENTS: Final = 20


def criar_parser_coletar() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kwai-collector coletar",
        description=(
            "Coleta os primeiros posts públicos de um perfil e seus comentários."
        ),
    )

    parser.add_argument(
        "perfil",
        help="Perfil do Kwai. Exemplo: @perfil_teste",
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
    )

    parser.add_argument(
        "--delay",
        type=numero_nao_negativo,
        default=settings.delay,
    )

    parser.add_argument(
        "--max-comments",
        type=limite_comentarios,
        default=DEFAULT_MAX_COMMENTS,
        help=(
            "Quantidade máxima de comentários principais por post. "
            "Informe um inteiro positivo ou 'todos'."
        ),
    )

    parser.add_argument(
        "--debug",
        action="store_true",
    )

    parser.add_argument(
        "--request-interval",
        type=numero_nao_negativo,
        default=settings.mobile_page_delay,
        help=("Intervalo mínimo entre requisições de comentários, em segundos."),
    )

    return parser


def criar_parser_buscar() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kwai-collector buscar",
        description=("Busca postagens públicas do Kwai por palavra-chave."),
    )

    parser.add_argument(
        "palavra_chave",
        help="Palavra-chave da busca.",
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
    )

    parser.add_argument(
        "--delay",
        type=numero_nao_negativo,
        default=settings.delay,
    )

    parser.add_argument(
        "--with-comments",
        action="store_true",
        help=("Coleta os comentários principais dos posts encontrados na busca."),
    )

    parser.add_argument(
        "--max-comments",
        type=limite_comentarios,
        default=DEFAULT_MAX_COMMENTS,
        help=(
            "Quantidade máxima de comentários por post. "
            "Informe um inteiro positivo ou 'todos'."
        ),
    )

    parser.add_argument(
        "--request-interval",
        type=numero_nao_negativo,
        default=settings.mobile_page_delay,
        help=("Intervalo mínimo entre requisições de comentários, em segundos."),
    )

    return parser


def criar_parser_perfil() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kwai-collector perfil",
        description=("Coleta postagens públicas de um perfil do Kwai."),
    )

    parser.add_argument(
        "perfil",
        help="Perfil do Kwai. Exemplo: @usuario",
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
    )

    parser.add_argument(
        "--delay",
        type=numero_nao_negativo,
        default=settings.delay,
    )

    return parser


def criar_parser_comentarios() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kwai-collector comentarios",
        description=("Coleta comentários públicos de uma postagem do Kwai."),
    )

    parser.add_argument(
        "postagem_url",
        help="URL da postagem ou photo_id.",
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
    )

    parser.add_argument(
        "--max-comments",
        type=limite_comentarios,
        default=DEFAULT_MAX_COMMENTS,
        help=(
            "Quantidade máxima de comentários principais. "
            "Informe um inteiro positivo ou 'todos'."
        ),
    )

    parser.add_argument(
        "--user-id",
        default=None,
        help=(
            "ID do autor da postagem. "
            "Pode ser necessário quando somente "
            "o photo_id for informado."
        ),
    )

    parser.add_argument(
        "--debug",
        action="store_true",
    )

    parser.add_argument(
        "--resume",
        action="store_true",
        help=("Retoma uma coleta interrompida a partir do progresso salvo."),
    )

    parser.add_argument(
        "--request-interval",
        type=numero_nao_negativo,
        default=settings.mobile_page_delay,
        help=("Intervalo mínimo entre requisições de comentários, em segundos."),
    )

    return parser


def mostrar_ajuda_principal() -> None:
    mensagem = """
Uso:
  kwai-collector buscar <palavra-chave> [opções]
  kwai-collector perfil <@usuario> [opções]
  kwai-collector comentarios <url-ou-photo-id> [opções]
  kwai-collector coletar <@usuario> [opções]
  kwai-collector <@usuario> [opções]

Comandos:
  buscar        Busca posts por palavra-chave.
  perfil        Coleta posts públicos de um perfil.
  comentarios   Coleta comentários de uma postagem.
  coletar       Coleta posts e comentários de um perfil.

Use:
  kwai-collector <comando> --help

para visualizar as opções específicas de cada comando.
""".strip()

    sys.stdout.write(f"{mensagem}\n")

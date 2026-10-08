"""Interface de linha de comando do coletor (Typer)."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Annotated

import typer
from pydantic import BaseModel, ValidationError

from ..application.exceptions import CollectionInterruptedError
from ..config import Settings
from ..container import Services, build_services
from ..domain.exceptions import InvalidInputError, KwaiApiError, KwaiCollectorError
from ..shared.logging_config import get_logger, setup_logging

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Coletor de postagens, engajamento e comentários do Kwai (VoxRadar · Nível 1).",
)
logger = get_logger("cli")

_EXIT_RUNTIME_ERROR = 1
_EXIT_INVALID_INPUT = 2

_API_ERROR_HINTS: dict[int, str] = {
    50: "verifique a assinatura: parâmetros enviados, sal e versão do app",
    11: "verifique os parâmetros e o contexto exigido pela rota",
    40: "verifique o client_key enviado e sua compatibilidade com a versão do app",
}

VerboseOption = Annotated[bool, typer.Option("--verbose", "-v", help="Logs em nível DEBUG.")]
OutOption = Annotated[
    Path | None,
    typer.Option("--out", "-o", help="Arquivo de saída JSON. Sem ele, imprime no stdout."),
]
LimitOption = Annotated[int, typer.Option("--limit", "-l", min=1, help="Máximo de itens.")]


def _write_output(items: Sequence[BaseModel], out: Path | None) -> None:
    payload = [item.model_dump() for item in items]
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if out is None:
        # Escreve em UTF-8 cru para não quebrar com emojis/acentos no console
        # do Windows (cp1252).
        sys.stdout.buffer.write((text + "\n").encode("utf-8"))
        sys.stdout.buffer.flush()
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text + "\n", encoding="utf-8")
    logger.info("%d registro(s) salvos em %s", len(items), out)


def _save_partial(items: Sequence[BaseModel], out: Path | None) -> None:
    """Grava o que a coleta interrompida já tinha; falha ao gravar só é registrada.

    A causa original da interrupção já é o erro do comando, então uma falha de
    escrita aqui não a esconde nem muda o código de saída.
    """
    try:
        _write_output(items, out)
    except OSError as exc:
        logger.error("falha ao escrever a saída parcial: %s", exc)


def _log_failure(action: str, error: KwaiCollectorError) -> None:
    """Registra o erro original e uma orientação, sem afirmar a causa do servidor."""
    logger.error("falha na coleta (%s): %s", action, error)
    cause = error.__cause__ if isinstance(error, CollectionInterruptedError) else error
    if isinstance(cause, KwaiApiError) and type(cause.result) is int:
        hint = _API_ERROR_HINTS.get(cause.result)
        if hint:
            logger.error("orientação: %s; causa exata não determinada", hint)


def _run(action: str, produce: Callable[[Services], list[BaseModel]], out: Path | None) -> None:
    try:
        settings = Settings()
        with build_services(settings) as services:
            items = produce(services)
        _write_output(items, out)
    except InvalidInputError as exc:
        logger.error("entrada inválida: %s", exc)
        raise typer.Exit(code=_EXIT_INVALID_INPUT) from exc
    except CollectionInterruptedError as exc:
        _log_failure(action, exc)
        logger.warning("gravando o resultado parcial")
        _save_partial(exc.partial, out)
        raise typer.Exit(code=_EXIT_RUNTIME_ERROR) from exc
    except KwaiCollectorError as exc:
        _log_failure(action, exc)
        raise typer.Exit(code=_EXIT_RUNTIME_ERROR) from exc
    except ValidationError as exc:
        logger.error("configuração inválida: %s", exc)
        raise typer.Exit(code=_EXIT_RUNTIME_ERROR) from exc
    except OSError as exc:
        logger.error("falha ao escrever a saída: %s", exc)
        raise typer.Exit(code=_EXIT_RUNTIME_ERROR) from exc


@app.command()
def busca(
    keyword: Annotated[
        list[str],
        typer.Option("--keyword", "-k", help="Palavra-chave (repita para várias)."),
    ],
    limit: LimitOption = 20,
    out: OutOption = None,
    verbose: VerboseOption = False,
) -> None:
    """Busca postagens por uma ou mais palavras-chave."""
    setup_logging(verbose=verbose)
    _run("busca", lambda s: list(s.search_posts.execute(keyword, limit=limit)), out)


@app.command()
def usuario(
    user: Annotated[str, typer.Option("--user", "-u", help="Conta do usuário (ex.: @perfil).")],
    limit: Annotated[
        int | None,
        typer.Option("--limit", "-l", min=1, help="Máximo de postagens (padrão: todas)."),
    ] = None,
    out: OutOption = None,
    verbose: VerboseOption = False,
) -> None:
    """Coleta as postagens de um usuário (API móvel, paginada)."""
    setup_logging(verbose=verbose)
    _run("usuario", lambda s: list(s.user_posts.execute(user, limit=limit)), out)


@app.command()
def comentarios(
    url: Annotated[str, typer.Option("--url", help="Link da postagem (.../@perfil/video/<id>).")],
    limit: Annotated[
        int | None,
        typer.Option("--limit", "-l", min=1, help="Máximo de comentários raiz (padrão: todos)."),
    ] = None,
    com_respostas: Annotated[
        bool,
        typer.Option(
            "--com-respostas",
            help="Inclui as respostas de cada comentário (saída expandida).",
        ),
    ] = False,
    out: OutOption = None,
    verbose: VerboseOption = False,
) -> None:
    """Coleta os comentários de uma postagem pelo link."""
    setup_logging(verbose=verbose)
    _run(
        "comentarios",
        lambda s: list(s.comments.execute(url, limit=limit, with_replies=com_respostas)),
        out,
    )

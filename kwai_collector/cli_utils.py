"""A1_Radar."""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from urllib.parse import urlparse


def numero_nao_negativo(value: str) -> float:
    try:
        numero = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("deve ser um número válido.") from exc

    if not math.isfinite(numero) or numero < 0:
        raise argparse.ArgumentTypeError("deve ser um número finito e não negativo.")

    return numero


def inteiro_positivo(value: str) -> int:
    try:
        numero = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "deve ser um número inteiro positivo."
        ) from exc

    if numero <= 0:
        raise argparse.ArgumentTypeError("deve ser um número inteiro positivo.")

    return numero


def inteiro_nao_negativo(value: str) -> int:
    try:
        numero = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "deve ser um número inteiro não negativo."
        ) from exc

    if numero < 0:
        raise argparse.ArgumentTypeError("não pode ser um número negativo.")

    return numero


def limite_comentarios(value: str) -> int | None:
    if value.strip().lower() == "todos":
        return None

    return inteiro_positivo(value)


def salvar_json(
    conteudo: object,
    arquivo_saida: Path,
) -> None:
    arquivo_saida.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with arquivo_saida.open(
        "w",
        encoding="utf-8",
    ) as arquivo:
        json.dump(
            conteudo,
            arquivo,
            ensure_ascii=False,
            indent=2,
        )


def limpar_usuario(usuario: str) -> str:
    usuario_limpo = usuario.strip().removeprefix("@")

    if not usuario_limpo:
        raise ValueError("Informe um perfil válido.")

    return usuario_limpo


def nome_arquivo_seguro(valor: str) -> str:
    nome = re.sub(
        r"[^a-zA-Z0-9._-]+",
        "_",
        valor,
    )

    return nome.strip("._-") or "resultado"


def extrair_photo_id(valor: str) -> str:
    valor = valor.strip()

    if valor.isdigit():
        return valor

    parsed = urlparse(valor)

    partes = [parte for parte in parsed.path.split("/") if parte]

    ids_numericos = [parte for parte in partes if parte.isdigit()]

    if ids_numericos:
        return ids_numericos[-1]

    raise ValueError("Não foi possível identificar o photo_id na URL informada.")

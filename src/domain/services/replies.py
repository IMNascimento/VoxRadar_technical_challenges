"""Regras das respostas de um comentário raiz: expansão e total declarado."""

from __future__ import annotations


def declares_replies(declared_replies: int | None) -> bool:
    """Indica se a raiz declara respostas a expandir.

    A regra usa truthiness: ``None`` e zero não expandem; um total negativo
    expande, embora não seja comparado por :func:`replies_diverge`.
    """
    return bool(declared_replies)


def replies_diverge(declared_replies: int | None, collected: int) -> bool:
    """Indica divergência entre o total declarado e as respostas entregues.

    Só compara total conhecido e não negativo; a divergência não indica causa.
    """
    return declared_replies is not None and declared_replies >= 0 and declared_replies != collected

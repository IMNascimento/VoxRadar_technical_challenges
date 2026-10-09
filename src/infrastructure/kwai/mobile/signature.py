"""Assinatura ``sig`` da API móvel anônima do Kwai (comentários e perfil).

Descoberta (09/2026, validada contra o app real): as rotas ``/rest/o/...`` do app
aceitam uma requisição **anônima** (sem login, sem cookies) assinada **apenas
com o ``sig``**:

    canonical = "".join("k=v" para chaves ordenadas, SEM separador,
                        valores já decodificados, exceto ``sig`` e os
                        tokens derivados ``__NS_sig3``/``__NStokensig``)
    sig       = MD5(canonical + SIG_SALT)   # hex minúsculo

O ``__NS_sig3`` **não** é necessário para estas rotas (verificado: sem ele a
resposta é ``result: 1`` com os dados) e, quando presente, **não** entra no
preimage do ``sig`` — o app o adiciona depois da assinatura. A assinatura cobre
os parâmetros da *query* **e** do corpo.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping

from .app_identity import SIG_SALT

# Tokens derivados que o app acrescenta após assinar; ficam fora do preimage.
_SIG_EXCLUDED: frozenset[str] = frozenset({"sig", "__NS_sig3", "__NStokensig"})


def compute_sig(params: Mapping[str, str]) -> str:
    """Calcula o ``sig`` do Kwai: ``MD5(canonical + SIG_SALT)`` em hex minúsculo.

    ``canonical`` concatena ``k=v`` das chaves em ordem alfabética **sem
    separador** (valores já decodificados), excluindo ``sig`` e os tokens
    derivados ``__NS_sig3``/``__NStokensig``.

    Args:
        params: parâmetros de query e corpo da requisição.

    Returns:
        Digest MD5 hexadecimal minúsculo.
    """
    canonical = "".join(
        f"{key}={value}" for key, value in sorted(params.items()) if key not in _SIG_EXCLUDED
    )
    return hashlib.md5((canonical + SIG_SALT).encode("utf-8")).hexdigest()

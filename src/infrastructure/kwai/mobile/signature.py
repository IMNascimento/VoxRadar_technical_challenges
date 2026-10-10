"""Assinatura ``sig`` da API móvel anônima do Kwai (comentários e perfil).

As rotas ``/rest/o/...`` aceitam requisição anônima (sem login nem cookies)
assinada só com o ``sig``, que cobre query e corpo::

    canonical = "".join("k=v" para chaves ordenadas, SEM separador,
                        valores já decodificados, exceto ``sig`` e os
                        tokens derivados ``__NS_sig3``/``__NStokensig``)
    sig       = MD5(canonical + SIG_SALT)   # hex minúsculo

Os tokens derivados são acrescentados pelo app depois de assinar e não são
necessários nestas rotas. Detalhes e evidências em ``docs/internals/signature.md``.
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

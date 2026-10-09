"""Cliente HTTP para o servico local de assinatura __NS_sig3 
(processo Java/unidbg em server/, ver PESQUISA.md). 
O algoritmo em si (emulacao nativa da libkwsgmain.so) 
vive em server/src/com/kwai/sig3/KwaiSign.java
aqui so chamamos a API HTTP que ele expoe (POST /sign, GET /health).
"""
from typing import Optional

import requests

from . import config
from .errors import Sig3ServiceUnavailableError


def _health(base_url: str, timeout: float) -> bool:
    try:
        resp = requests.get(f"{base_url}/health", timeout=timeout)
        return resp.status_code == 200 and resp.text == "ok"
    except requests.RequestException:
        return False


def _sign(base_url: str, timeout: float, string_to_sign: str) -> Optional[str]:
    resp = requests.post(
        f"{base_url}/sign",
        data=string_to_sign.encode("utf-8"),
        timeout=timeout,
    )
    if resp.status_code == 204:
        return None
    resp.raise_for_status()
    return resp.text


def assinar(string_to_sign: str) -> str:
    """Retorna o __NS_sig3 (hex) para a string de assinatura fornecida.
    Levanta Sig3ServiceUnavailableError se o servico local nao estiver
    no ar ou nao responder um valor valido."""
    base_url = config.SIG3_SERVICE_URL
    timeout = config.HTTP_TIMEOUT_SECONDS

    if not _health(base_url, timeout):
        raise Sig3ServiceUnavailableError(
            f"servico de assinatura __NS_sig3 nao esta respondendo em {base_url}. "
            'Suba com: cmd.exe /c "server\\run.bat --serve 8765"'
        )
    try:
        resultado = _sign(base_url, timeout, string_to_sign)
    except Exception as e:
        raise Sig3ServiceUnavailableError(f"erro ao chamar o servico de assinatura: {e}") from e
    if not resultado:
        raise Sig3ServiceUnavailableError("o servico de assinatura retornou vazio/null")
    return resultado

"""Identidade do app Kwai que a API móvel espera: versão, chave do cliente e sal do ``sig``.

Estes valores valem **juntos**. O sal do ``sig`` só foi provado para a versão do
app abaixo (Kwai Lite): assinar com outra versão (medido: ``appver`` 13.7) é
rejeitado com ``result: 50`` (*Failed to verify the signature*). Ao atualizar
``APP_VERSION``, capture um request real do app, revalide o sal e troque o vetor
de ``tests/test_mobile_api.py`` — o teste de versão falha até isso acontecer.
"""

from __future__ import annotations

# Kwai Lite instalado no dispositivo de referência.
APP_VERSION: str = "10.3.20.539600"
# ``client_key`` enviado no corpo; sem ele a API responde ``result: 40``.
CLIENT_KEY: str = "3c2cd3f3"
# Sal do ``sig`` (MD5), válido para ``APP_VERSION``.
SIG_SALT: str = "382700b563f4"
# O app usa este UA; a resposta é idêntica sem ele (mantido por fidelidade).
APP_USER_AGENT: str = "kwai-android"

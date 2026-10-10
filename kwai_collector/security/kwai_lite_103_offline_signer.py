"""Assinatura ``sig`` do Kwai Lite 10.3.20.540101 sem Android.

O algoritmo foi conferido com o ``getClock`` do APK ``kwai.lite.video``
10.3.20.540101 e com vetores sintéticos capturados da função nativa.
Ele não calcula ``__NS_sig3`` nem campos de sessão.

A1_Radar.
"""

from __future__ import annotations

import hashlib


class KwaiLite103OfflineSigner:
    """Implementa ``NativeSigner`` para a versão específica do Kwai Lite."""

    APP_PACKAGE = "kwai.lite.video"
    APP_VERSION = "10.3.20.540101"
    _SUFFIX = b"382700b563f4"

    def __init__(
        self,
        *,
        app_package: str = APP_PACKAGE,
        app_version: str = APP_VERSION,
    ) -> None:
        if app_package != self.APP_PACKAGE or app_version != self.APP_VERSION:
            raise ValueError(
                "Este assinador só foi validado para "
                f"{self.APP_PACKAGE} {self.APP_VERSION}."
            )

    def sign(self, canonical_bytes: bytes) -> str:
        if not isinstance(canonical_bytes, bytes):
            raise TypeError("canonical_bytes deve ser bytes.")
        if not canonical_bytes:
            raise ValueError("canonical_bytes não pode ser vazio.")

        return hashlib.md5(
            canonical_bytes + self._SUFFIX,
            usedforsecurity=False,
        ).hexdigest()

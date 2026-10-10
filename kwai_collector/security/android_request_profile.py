"""A1_Radar."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class AndroidRequestProfile:
    """
    Contexto estável da requisição mobile.

    Este módulo NÃO gera assinatura, token,
    identificador de dispositivo ou sessão.

    Ele apenas monta parâmetros de protocolo
    compatíveis com o fluxo Android observado.
    """

    app: str = "1"
    os: str = "android"
    kpf: str = "ANDROID_PHONE"
    kpn: str = "KWAI"
    pkg: str = "kwai.lite.video"
    language: str = "pt-br"
    country_code: str = "br"

    def build_query_fields(
        self,
    ) -> dict[str, str]:
        return {
            "app": self.app,
            "os": self.os,
            "kpf": self.kpf,
            "kpn": self.kpn,
            "pkg": self.pkg,
            "language": self.language,
            "country_code": self.country_code,
            "timestamp": self._timestamp_ms(),
        }

    def build_body_fields(
        self,
    ) -> dict[str, str]:
        return {}

    def build_header_fields(
        self,
    ) -> dict[str, str]:
        return {
            "Accept": ("application/json, text/plain, */*"),
            "Content-Type": ("application/x-www-form-urlencoded"),
        }

    @staticmethod
    def _timestamp_ms() -> str:
        agora = datetime.now(UTC)

        return str(int(agora.timestamp() * 1000))

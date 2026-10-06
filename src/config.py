"""Configuração tipada via variáveis de ambiente (``pydantic-settings``)."""

from __future__ import annotations

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)


class Settings(BaseSettings):
    """Configuração do coletor, lida de ``.env`` e do ambiente.

    Todos os campos têm padrões seguros; nenhum segredo é obrigatório.
    """

    model_config = SettingsConfigDict(
        env_prefix="KWAI_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    request_delay: float = Field(
        default=1.5,
        ge=0.0,
        description="Intervalo mínimo, em segundos, entre requisições (rate limit).",
    )
    http_timeout: float = Field(
        default=20.0,
        gt=0.0,
        description="Timeout de cada requisição HTTP, em segundos.",
    )
    max_retries: int = Field(
        default=3,
        ge=0,
        description="Tentativas extras em falhas transitórias (retry com backoff).",
    )
    user_agent: str = Field(
        default=DEFAULT_USER_AGENT,
        description="User-Agent enviado nas requisições web (busca e perfil).",
    )

    @field_validator("user_agent", mode="before")
    @classmethod
    def _normalize_user_agent(cls, value: object) -> str:
        """Normaliza o UA: vazio ou ausente vira o padrão; caso contrário, ``strip``."""
        if value is None:
            return DEFAULT_USER_AGENT
        text = str(value).strip()
        return text or DEFAULT_USER_AGENT

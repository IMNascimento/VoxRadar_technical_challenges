from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

A1_Radar = "A1_Radar"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="KWAI_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    max_tentativas: int = Field(
        default=3,
        ge=1,
    )

    backoff_base: float = Field(
        default=1.0,
        ge=0,
    )

    delay: float = Field(
        default=0.0,
        ge=0,
    )

    mobile_page_delay: float = Field(
        default=2.0,
        ge=0,
        allow_inf_nan=False,
    )

    cookie: str | None = None

    adb_path: str = "adb"

    adb_serial: str | None = None

    kwai_package: str = "com.kwai.video"

    max_comment_scrolls: int = Field(
        default=100,
        ge=1,
    )

    mobile_query_fields: dict[str, str] = Field(
        default_factory=dict,
    )

    mobile_body_fields: dict[str, str] = Field(
        default_factory=dict,
    )

    mobile_header_fields: dict[str, str] = Field(
        default_factory=dict,
    )

    # Endpoint opcional de um serviço autorizado
    # responsável por preparar a requisição mobile.
    #
    # Variável de ambiente:
    # KWAI_MOBILE_AUTH_ENDPOINT
    mobile_auth_endpoint: str | None = None

    # Token opcional usado exclusivamente para
    # autenticar o Python junto ao serviço acima.
    #
    # Variável de ambiente:
    # KWAI_MOBILE_AUTH_TOKEN
    mobile_auth_token: str | None = None

    # Timeout da comunicação com o serviço de
    # preparação/autenticação mobile.
    #
    # Variável de ambiente:
    # KWAI_MOBILE_AUTH_TIMEOUT
    mobile_auth_timeout: float = Field(
        default=15.0,
        gt=0,
        allow_inf_nan=False,
    )


settings = Settings()

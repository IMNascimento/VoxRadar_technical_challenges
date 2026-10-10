from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # lê do ambiente ou do .env, ex: KWAI_REQUEST_DELAY=3
    model_config = SettingsConfigDict(env_prefix="KWAI_", env_file=".env", extra="ignore")

    request_delay: float = Field(default=1.5, ge=0)  # segundos entre requests
    http_timeout: float = Field(default=20.0, gt=0)
    max_retries: int = Field(default=3, ge=0)
    # user agent de navegador, usado só na busca (site)
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    )


settings = Settings()

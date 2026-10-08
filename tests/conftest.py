"""Fixtures compartilhadas dos testes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.config import Settings

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> Any:
    """Carrega uma fixture JSON pelo nome de arquivo."""
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def search_response() -> dict[str, Any]:
    return load_fixture("search_response.json")


@pytest.fixture
def profile_feeds() -> dict[str, Any]:
    return load_fixture("profile_feeds.json")


@pytest.fixture
def settings() -> Settings:
    """Settings determinísticas para teste: sem rate limit nem retries."""
    return Settings(request_delay=0.0, http_timeout=5.0, max_retries=0)


@pytest.fixture
def retry_settings() -> Settings:
    """Settings com 2 retries extras (3 tentativas), sem rate limit."""
    return Settings(request_delay=0.0, http_timeout=5.0, max_retries=2)


@pytest.fixture
def no_backoff(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Neutraliza o ``sleep`` do backoff do tenacity e devolve os intervalos pedidos."""
    waits: list[float] = []
    monkeypatch.setattr("tenacity.nap.time.sleep", waits.append)
    return waits

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
def profile_html() -> str:
    return (FIXTURES / "profile_page.html").read_text(encoding="utf-8")


@pytest.fixture
def settings() -> Settings:
    """Settings determinísticas para teste: sem rate limit nem retries."""
    return Settings(request_delay=0.0, http_timeout=5.0, max_retries=0)

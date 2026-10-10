import json
from pathlib import Path
from typing import Any

import pytest

from kwai_collector.config import settings

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def no_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    # nos testes não precisa esperar delay nem backoff
    monkeypatch.setattr(settings, "request_delay", 0)
    monkeypatch.setattr(settings, "max_retries", 1)
    monkeypatch.setattr("kwai_collector.client.time.sleep", lambda seconds: None)

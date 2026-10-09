"""Limitador de intervalo mínimo entre requisições de um cliente HTTP do Kwai.

Cada cliente (web e móvel) cria a própria instância: as duas APIs falam com
hosts distintos, então o limite é independente por cliente, sem estado compartilhado.
"""

from __future__ import annotations

import threading
import time


class RateLimiter:
    """Garante um intervalo mínimo entre chamadas (thread-safe)."""

    def __init__(self, min_interval: float) -> None:
        """Inicializa o limitador.

        Args:
            min_interval: intervalo mínimo em segundos; ``0`` desliga o atraso.
        """
        self._min_interval = min_interval
        self._lock = threading.Lock()
        self._last = 0.0

    def wait(self) -> None:
        """Bloqueia até completar o intervalo mínimo desde a última chamada."""
        if self._min_interval <= 0:
            return
        with self._lock:
            elapsed = time.monotonic() - self._last
            sleep_for = self._min_interval - elapsed
            if sleep_for > 0:
                time.sleep(sleep_for)
            self._last = time.monotonic()

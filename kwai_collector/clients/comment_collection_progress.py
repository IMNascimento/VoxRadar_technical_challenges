"""Progress that can be saved without storing a signed request or session tokens.

A1_Radar.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CommentCollectionProgress:
    photo_id: str
    user_id: str
    llsid: str
    pcursor: str
    comments: list[dict[str, Any]]
    complete: bool = False


class CommentCollectionInterrupted(RuntimeError):
    """A collection stopped with its last successful pages still available.

    ``message`` must describe the failure without including request URLs,
    headers, tokens, or arbitrary server response text.
    """

    def __init__(
        self,
        message: str,
        progress: CommentCollectionProgress,
    ) -> None:
        super().__init__(message)
        self.progress = progress

"""A1_Radar."""

from pathlib import Path
from typing import Protocol

from kwai_collector.models.comentario import Comentario
from kwai_collector.parsers.ui_comments import parse_ui_comments_xml


class CommentProvider(Protocol):
    def get_comments(
        self,
        postagem_url: str,
    ) -> list[Comentario]: ...


class XmlCommentProvider:
    def __init__(self, arquivo_xml: Path) -> None:
        self.arquivo_xml = arquivo_xml

    def get_comments(
        self,
        postagem_url: str,
    ) -> list[Comentario]:
        return parse_ui_comments_xml(
            arquivo_xml=self.arquivo_xml,
            postagem_url=postagem_url,
        )

"""A1_Radar."""

import xml.etree.ElementTree as ET
from pathlib import Path

from kwai_collector.models.comentario import Comentario
from kwai_collector.parsers.comment_parser import parse_ui_comment


def buscar_texto(
    container: ET.Element,
    final_resource_id: str,
) -> str | None:
    for node in container.iter():
        resource_id = node.attrib.get("resource-id", "")

        if resource_id.endswith(final_resource_id):
            return node.attrib.get("text") or None

    return None


def parse_ui_comments_xml(
    arquivo_xml: Path,
    postagem_url: str,
) -> list[Comentario]:
    tree = ET.parse(arquivo_xml)
    root = tree.getroot()

    resultados: list[Comentario] = []

    chaves_encontradas: set[tuple[str | None, str, str | None]] = set()

    for container in root.iter():
        resource_id = container.attrib.get("resource-id", "")

        if not resource_id.endswith(":id/comment_frame"):
            continue

        autor = buscar_texto(
            container,
            ":id/name",
        )

        texto = buscar_texto(
            container,
            ":id/comment",
        )

        curtidas = buscar_texto(
            container,
            ":id/tv_comment_like_count",
        )

        data = buscar_texto(
            container,
            ":id/created",
        )

        if not texto:
            continue

        chave = (
            autor,
            texto,
            data,
        )

        if chave in chaves_encontradas:
            continue

        chaves_encontradas.add(chave)

        comentario = parse_ui_comment(
            autor=autor,
            texto=texto,
            curtidas=curtidas,
            data=data,
            postagem_url=postagem_url,
        )

        resultados.append(comentario)

    return resultados

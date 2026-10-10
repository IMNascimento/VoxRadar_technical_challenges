"""A1_Radar."""

import re
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path

from kwai_collector.config import settings
from kwai_collector.models.comentario import Comentario
from kwai_collector.parsers.ui_comments import parse_ui_comments_xml


class AdbCommentProvider:
    def __init__(
        self,
        arquivo_xml: Path = Path("window.xml"),
        video_xml: Path = Path("video.xml"),
    ) -> None:
        self.arquivo_xml = arquivo_xml
        self.video_xml = video_xml

    def _adb_command(
        self,
        *args: str,
    ) -> list[str]:
        comando = [settings.adb_path]

        if settings.adb_serial:
            comando.extend(
                [
                    "-s",
                    settings.adb_serial,
                ]
            )

        comando.extend(args)

        return comando

    def _capturar_xml(
        self,
        arquivo_remoto: str,
        arquivo_local: Path,
    ) -> None:
        ultimo_erro: subprocess.CalledProcessError | None = None

        for tentativa in range(
            1,
            settings.max_tentativas + 1,
        ):
            try:
                subprocess.run(
                    self._adb_command(
                        "shell",
                        "uiautomator",
                        "dump",
                        arquivo_remoto,
                    ),
                    check=True,
                )

                subprocess.run(
                    self._adb_command(
                        "pull",
                        arquivo_remoto,
                        str(arquivo_local),
                    ),
                    check=True,
                )

                return

            except subprocess.CalledProcessError as erro:
                ultimo_erro = erro

                if tentativa == settings.max_tentativas:
                    break

                espera = settings.backoff_base * tentativa

                time.sleep(espera)

        if ultimo_erro is not None:
            raise ultimo_erro

        raise RuntimeError("Não foi possível capturar o XML via ADB.")

    def _abrir_post(
        self,
        postagem_url: str,
    ) -> None:
        subprocess.run(
            self._adb_command(
                "shell",
                "am",
                "start",
                "-W",
                "-a",
                "android.intent.action.VIEW",
                "-d",
                postagem_url,
                "-p",
                settings.kwai_package,
            ),
            check=True,
        )

        time.sleep(3.0)

    def _abrir_comentarios(self) -> None:
        self._capturar_xml(
            "/sdcard/video.xml",
            self.video_xml,
        )

        tree = ET.parse(self.video_xml)

        root = tree.getroot()

        for node in root.iter():
            resource_id = node.attrib.get(
                "resource-id",
                "",
            )

            if resource_id != "com.kwai.video.basis:id/comment_button":
                continue

            bounds = node.attrib.get(
                "bounds",
                "",
            )

            numeros = [
                int(numero)
                for numero in re.findall(
                    r"-?\d+",
                    bounds,
                )
            ]

            if len(numeros) != 4:
                raise RuntimeError(
                    "Não foi possível identificar a posição do botão de comentários."
                )

            x1, y1, x2, y2 = numeros

            x = (x1 + x2) // 2
            y = (y1 + y2) // 2

            subprocess.run(
                self._adb_command(
                    "shell",
                    "input",
                    "tap",
                    str(x),
                    str(y),
                ),
                check=True,
            )

            return

        raise RuntimeError("Botão de comentários não encontrado.")

    def _rolar_comentarios(self) -> None:
        subprocess.run(
            self._adb_command(
                "shell",
                "input",
                "swipe",
                "540",
                "1800",
                "540",
                "950",
                "500",
            ),
            check=True,
        )

        time.sleep(1.0)

    def get_comments(
        self,
        postagem_url: str,
    ) -> list[Comentario]:
        self._abrir_post(
            postagem_url,
        )

        self._abrir_comentarios()

        time.sleep(1.5)

        resultados: list[Comentario] = []

        chaves_encontradas: set[tuple[str | None, str, object]] = set()

        tentativas_sem_novos = 0

        max_scrolls = settings.max_comment_scrolls

        for _ in range(max_scrolls):
            self._capturar_xml(
                "/sdcard/window.xml",
                self.arquivo_xml,
            )

            comentarios_visiveis = parse_ui_comments_xml(
                arquivo_xml=self.arquivo_xml,
                postagem_url=postagem_url,
            )

            if not comentarios_visiveis:
                time.sleep(1.0)
                continue

            novos = 0

            for comentario in comentarios_visiveis:
                chave = (
                    comentario.autor.usuario,
                    comentario.texto,
                    comentario.data,
                )

                if chave in chaves_encontradas:
                    continue

                chaves_encontradas.add(chave)

                resultados.append(comentario)

                novos += 1

            if novos == 0:
                tentativas_sem_novos += 1
            else:
                tentativas_sem_novos = 0

            if tentativas_sem_novos >= 2:
                break

            self._rolar_comentarios()

        return resultados

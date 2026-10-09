"""
Download de video/thumbnail de uma Postagem (rota web).

Baixa para `{pasta_video}/media/{video,img}/{video,thumbnail}.<ext>`.
Falhas de download (midia ausente, erro de rede) NAO interrompem a
coleta: sao avisadas em stderr e a funcao segue para o proximo arquivo.
"""
import sys
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests

from . import config


def _extensao_midia(url: str, extensao_padrao: str) -> str:
    caminho = urlparse(url).path
    extensao = Path(caminho).suffix
    return extensao if extensao else extensao_padrao


def _baixar_arquivo(url: str, destino: Path) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    resp = requests.get(
        url,
        headers={"User-Agent": config.WEB_USER_AGENT},
        timeout=config.HTTP_TIMEOUT_SECONDS,
        stream=True,
    )
    resp.raise_for_status()
    with open(destino, "wb") as f:
        for chunk in resp.iter_content(chunk_size=65536):
            if chunk:
                f.write(chunk)


def baixar_midia(postagem: dict, pasta_video: Path) -> None:
    """Baixa video e thumbnail de `postagem` (precisa ter o campo extra
    `midia.video_url`/`midia.thumbnail_url`, preenchido pelo web_client)
    para dentro de `pasta_video`."""
    photo_id = postagem.get("id") or "sem_id"
    midia = postagem.get("midia") or {}

    arquivos = (
        (midia.get("video_url"), "video", "video", ".mp4"),
        (midia.get("thumbnail_url"), "img", "thumbnail", ".webp"),
    )
    for url, subpasta, nome, extensao_padrao in arquivos:
        if not url:
            print(f"[aviso] {nome} indisponivel para {photo_id}.", file=sys.stderr)
            continue

        destino = pasta_video / "media" / subpasta / f"{nome}{_extensao_midia(url, extensao_padrao)}"
        time.sleep(config.MEDIA_DOWNLOAD_DELAY_SECONDS)
        try:
            _baixar_arquivo(url, destino)
            print(f"[ok] {nome} salvo em {destino}")
        except requests.RequestException as erro:
            print(f"[aviso] nao foi possivel baixar {nome} de {photo_id}: {erro}", file=sys.stderr)

"""
Construtores dos schemas `Postagem` e `Comentario`. 
Especificados em docs/schemas.md.
"""
from datetime import datetime, timezone
from typing import Optional


def now_iso() -> str:
    """Timestamp ISO-8601 UTC do momento da coleta, ex: 2026-07-27T14:30:00Z."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ms_timestamp_to_iso(ms: Optional[int]) -> Optional[str]:
    """Converte um timestamp em milissegundos para ISO-8601 UTC. 
    Retorna None se `ms` for None/invalido."""
    if ms is None:
        return None
    try:
        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
    except (ValueError, OSError, OverflowError):
        return None


def build_postagem(
    *,
    id_: Optional[str],
    url: str,
    autor_usuario: Optional[str],
    autor_id: Optional[str],
    autor_url_perfil: Optional[str],
    texto: Optional[str],
    data_publicacao: Optional[str],
    curtidas: Optional[int],
    comentarios: Optional[int],
    compartilhamentos: Optional[int],
    visualizacoes: Optional[int],
    video_url: Optional[str] = None,
    thumbnail_url: Optional[str] = None,
) -> dict:
    return {
        "id": id_,
        "url": url,
        "autor": {
            "usuario": autor_usuario,
            "id": autor_id,
            "url_perfil": autor_url_perfil,
        },
        "texto": texto,
        "data_publicacao": data_publicacao,
        "engajamento": {
            "curtidas": curtidas,
            "comentarios": comentarios,
            "compartilhamentos": compartilhamentos,
            "visualizacoes": visualizacoes,
        },
        # Campo extra (fora do schemas.md oficial, que so exige
        # url/engajamento/coletado_em) -- usado por `--baixar-midia`.
        "midia": {
            "video_url": video_url,
            "thumbnail_url": thumbnail_url,
        },
        "coletado_em": now_iso(),
    }


def build_perfil(
    *,
    usuario: Optional[str],
    id_: Optional[str],
    nome: Optional[str],
    bio: Optional[str],
    verificado: Optional[bool],
    avatar_url: Optional[str],
    seguidores: Optional[int],
    seguindo: Optional[int],
    total_postagens: Optional[int],
    url_perfil: str,
) -> dict:
    """Schema `Perfil` -- nao faz parte do schemas.md original (que cobre
    so Postagem/Comentario), e uma extensao pedida para a funcionalidade
    `usuario --perfil`. Documentado em PESQUISA.md."""
    return {
        "usuario": usuario,
        "id": id_,
        "nome": nome,
        "bio": bio,
        "verificado": verificado,
        "avatar_url": avatar_url,
        "seguidores": seguidores,
        "seguindo": seguindo,
        "total_postagens": total_postagens,
        "url_perfil": url_perfil,
        "coletado_em": now_iso(),
    }


def build_comentario(
    *,
    id_: Optional[str],
    postagem_url: str,
    autor_usuario: Optional[str],
    autor_id: Optional[str],
    texto: str,
    curtidas: Optional[int],
    data: Optional[str],
    respondendo_a: Optional[str] = None,
) -> dict:
    return {
        "id": id_,
        "postagem_url": postagem_url,
        "autor": {
            "usuario": autor_usuario,
            "id": autor_id,
        },
        "texto": texto,
        "curtidas": curtidas,
        "data": data,
        # Campo extra (fora do schemas.md oficial): id do comentario
        # principal ao qual este responde -- None para comentarios
        # principais, preenchido para sub-comentarios (ver PESQUISA.md).
        "respondendo_a": respondendo_a,
        "coletado_em": now_iso(),
    }

"""CLI do kwai_collector. Ver README.md para exemplos de uso.

Estrutura de saida (ver README.md):

    out/
    └── <usuario-ou-palavra-chave>/
        ├── perfil.json          (so para `usuario --perfil`)
        ├── usuario.json          (so para `usuario`: lista de postagens)
        └── <id_do_video>/
            ├── postagem.json
            ├── comentarios.json 
            └── media/
                ├── img/thumbnail.webp
                └── video/video.mp4
"""
import argparse
import json
import re
import sys
from pathlib import Path

from .errors import CollectorError


def _slug(texto: str) -> str:
    """Normaliza um nome de usuario/palavra-chave para um nome de pasta
    seguro (sem espacos nem caracteres especiais de filesystem)."""
    texto = texto.strip().lstrip("@")
    texto = re.sub(r"\s+", "_", texto)
    texto = re.sub(r"[^A-Za-z0-9_.\-]", "", texto)
    return texto or "saida"


def _gravar_json(dados, caminho: Path) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)


def _escrever_saida(dados: list, out_path: str) -> None:
    path = Path(out_path)
    _gravar_json(dados, path)
    print(f"[ok] {len(dados)} item(ns) salvo(s) em {path}")


def _coletar_comentarios_melhor_esforco(url: str, limit: int, com_subcomentarios: bool = False):
    from . import mobile_client

    try:
        return mobile_client.comentarios_de_postagem(
            url, limit=limit, incluir_subcomentarios=com_subcomentarios
        )
    except CollectorError as e:
        print(f"[aviso] nao foi possivel coletar comentarios de '{url}': {e}", file=sys.stderr)
        return None


def cmd_busca(args: argparse.Namespace) -> int:
    from . import midia, web_client

    pasta_raiz = Path("out") / _slug(args.keyword)
    postagens = web_client.buscar_por_palavra_chave(args.keyword, limit=args.limit)

    for postagem in postagens:
        video_id = postagem.get("id")
        if not video_id:
            print("[aviso] postagem sem id, pulando (sem pasta dedicada).", file=sys.stderr)
            continue

        pasta_video = pasta_raiz / video_id
        _gravar_json(postagem, pasta_video / "postagem.json")

        if not args.sem_comentarios:
            comentarios = _coletar_comentarios_melhor_esforco(
                postagem["url"], limit=50, com_subcomentarios=args.com_subcomentarios
            )
            if comentarios is not None:
                _gravar_json(comentarios, pasta_video / "comentarios.json")
                print(f"[ok] {len(comentarios)} comentario(s) de {video_id} salvos")

        if args.baixar_midia:
            midia.baixar_midia(postagem, pasta_video)

    print(f"[ok] {len(postagens)} postagem(ns) salva(s) em {pasta_raiz}")
    return 0


def cmd_usuario(args: argparse.Namespace) -> int:
    from . import midia, web_client

    handle = web_client.normalizar_handle(args.user)
    pasta_raiz = Path("out") / _slug(handle)

    perfil, postagens = web_client.carregar_perfil(args.user, limit=args.limit)

    out_path = Path(args.out) if args.out else pasta_raiz / "usuario.json"
    _escrever_saida(postagens, str(out_path))
    if len(postagens) < args.limit:
        print(
            f"[aviso] foram encontradas {len(postagens)} postagem(ns), menos que o limite "
            f"pedido ({args.limit}) -- o perfil nao tem mais postagens publicas disponiveis"
        )

    if args.perfil:
        if perfil is None:
            print(
                f"[aviso] nao foi possivel coletar dados de perfil de '{handle}' "
                "(ver TROUBLESHOOTING.md)",
                file=sys.stderr,
            )
        else:
            caminho = pasta_raiz / "perfil.json"
            _gravar_json(perfil, caminho)
            print(f"[ok] perfil salvo em {caminho}")

    if args.comentarios or args.baixar_midia:
        for postagem in postagens:
            video_id = postagem.get("id")
            if not video_id:
                print("[aviso] postagem sem id, pulando (sem pasta dedicada).", file=sys.stderr)
                continue

            pasta_video = pasta_raiz / video_id
            _gravar_json(postagem, pasta_video / "postagem.json")

            if args.comentarios:
                comentarios = _coletar_comentarios_melhor_esforco(
                    postagem["url"], limit=args.comentarios_limit,
                    com_subcomentarios=args.com_subcomentarios,
                )
                if comentarios is not None:
                    _gravar_json(comentarios, pasta_video / "comentarios.json")
                    print(f"[ok] {len(comentarios)} comentario(s) de {video_id} salvos")

            if args.baixar_midia:
                midia.baixar_midia(postagem, pasta_video)

    return 0


def cmd_comentarios(args: argparse.Namespace) -> int:
    from . import mobile_client

    resultados = mobile_client.comentarios_de_postagem(
        args.url, limit=args.limit, incluir_subcomentarios=args.com_subcomentarios
    )
    _escrever_saida(resultados, args.out)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kwai_collector",
        description="Coletor de dados publicos do Kwai (busca, postagens de usuario, comentarios).",
    )
    sub = parser.add_subparsers(dest="comando", required=True)

    p_busca = sub.add_parser("busca", help="Busca postagens por palavra-chave")
    p_busca.add_argument("--keyword", required=True, help="Palavra-chave a buscar")
    p_busca.add_argument("--limit", type=int, default=50, help="Quantidade maxima de postagens (padrao: 50)")
    p_busca.add_argument(
        "--sem-comentarios",
        action="store_true",
        help="Nao coleta comentarios de cada postagem (por padrao, coleta por melhor esforco)",
    )
    p_busca.add_argument(
        "--baixar-midia",
        action="store_true",
        help="Baixa video e thumbnail de cada postagem coletada",
    )
    p_busca.add_argument(
        "--com-subcomentarios",
        action="store_true",
        help="Tambem busca as respostas (sub-comentarios) de cada comentario principal "
        "(1 chamada extra por comentario com resposta -- pode deixar a coleta bem mais lenta)",
    )
    p_busca.set_defaults(func=cmd_busca)

    p_usuario = sub.add_parser("usuario", help="Coleta perfil e postagens de um usuario")
    p_usuario.add_argument("--user", required=True, help='Usuario/handle ou URL do perfil, ex: "@perfil"')
    p_usuario.add_argument("--limit", type=int, default=50, help="Quantidade maxima de postagens (padrao: 50)")
    p_usuario.add_argument(
        "--out", default=None, help="Caminho do JSON de saida (padrao: out/<usuario>/usuario.json)"
    )
    p_usuario.add_argument(
        "--perfil",
        action="store_true",
        help="Tambem salva out/<usuario>/perfil.json (bio, seguidores, seguindo, etc.)",
    )
    p_usuario.add_argument(
        "--baixar-midia",
        action="store_true",
        help="Baixa video e thumbnail de cada postagem coletada",
    )
    p_usuario.add_argument(
        "--comentarios",
        action="store_true",
        help="Tambem coleta os comentarios de cada postagem",
    )
    p_usuario.add_argument(
        "--comentarios-limit",
        type=int,
        default=50,
        help="Quantidade maxima de comentarios por postagem (padrao: 50)",
    )
    p_usuario.add_argument(
        "--com-subcomentarios",
        action="store_true",
        help="Com --comentarios, tambem busca as respostas de cada comentario principal "
        "(1 chamada extra por comentario com resposta -- pode deixar a coleta bem mais lenta)",
    )
    p_usuario.set_defaults(func=cmd_usuario)

    p_comentarios = sub.add_parser("comentarios", help="Coleta os comentarios de uma postagem")
    p_comentarios.add_argument("--url", required=True, help="URL da postagem (.../@user/video/ID)")
    p_comentarios.add_argument("--limit", type=int, default=50, help="Quantidade maxima de comentarios (padrao: 50)")
    p_comentarios.add_argument("--out", required=True, help="Caminho do arquivo JSON de saida")
    p_comentarios.add_argument(
        "--com-subcomentarios",
        action="store_true",
        help="Tambem busca as respostas (sub-comentarios) de cada comentario principal "
        "(1 chamada extra por comentario com resposta -- pode deixar a coleta bem mais lenta)",
    )
    p_comentarios.set_defaults(func=cmd_comentarios)

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except CollectorError as e:
        print(f"[erro] {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n[cancelado pelo usuario]", file=sys.stderr)
        return 130
    except Exception as e:  # erro inesperado -- nunca deixar a ferramenta
        # quebrar sem mensagem (requisito do nivel 0).
        print(f"[erro inesperado] {type(e).__name__}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

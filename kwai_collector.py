"""
Módulo principal do coletor Kwai via Playwright.

VoxRadar · Desafio Kwai · A1_Radar

Três modos de execução:
    busca       — postagens por palavra-chave
    usuario     — postagens de um perfil
    comentarios — comentários de uma postagem
"""

import argparse
import html
import json
import os
from datetime import datetime, timezone
from urllib.parse import quote

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

CONFIG = {
    "headless":        os.getenv("KWAI_HEADLESS", "false").lower() == "true",
    "goto_timeout":    int(os.getenv("KWAI_GOTO_TIMEOUT", "30000")),
    "wait_after_load": int(os.getenv("KWAI_WAIT_AFTER_LOAD", "6000")),
    "scroll_wait":     int(os.getenv("KWAI_SCROLL_WAIT", "2000")),
    "user_agent":      os.getenv("KWAI_USER_AGENT",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
}


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------

def _agora_iso() -> str:
    """Timestamp UTC em ISO-8601 (ex.: 2026-09-11T14:30:00Z)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _str_ou_none(valor):
    """Retorna string limpa, ou None se vazio/ausente."""
    if valor is None:
        return None
    texto = str(valor).strip()
    return texto if texto else None


def _normalizar_data(valor):
    """Converte epoch (s ou ms) para ISO-8601 UTC. Retorna None se inválido."""
    if valor is None:
        return None
    try:
        if isinstance(valor, str) and valor.isdigit():
            valor = int(valor)
        if isinstance(valor, (int, float)):
            ts = valor / 1000 if valor > 1e11 else valor
            return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, OSError, OverflowError):
        pass
    return None


def _abrir_contexto(p):
    """Abre Chromium + contexto + página com a config do .env."""
    browser = p.chromium.launch(headless=CONFIG["headless"])
    context = browser.new_context(
        user_agent=CONFIG["user_agent"],
        viewport={"width": 1280, "height": 720},
    )
    return browser, context, context.new_page()


def salvar_json(dados, caminho_arquivo):
    """Salva JSON garantindo a criação do diretório."""
    try:
        diretorio = os.path.dirname(caminho_arquivo)
        if diretorio:
            os.makedirs(diretorio, exist_ok=True)
        with open(caminho_arquivo, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
        print(f"Dados salvos em: {caminho_arquivo}")
    except OSError as e:
        print(f"Erro ao salvar {caminho_arquivo}: {e}")
        raise


# ------------------------------------------------------------
# Montagem de objetos (aderente a docs/schemas.md)
# ------------------------------------------------------------

def _montar_postagem(feed, keyword=None, user_clean=None):
    """Monta um objeto Postagem a partir de um feed da API do Kwai."""
    photo_id = _str_ou_none(feed.get("photo_id_str") or feed.get("photo_id"))
    kwai_id = _str_ou_none(feed.get("kwai_id"))

    if kwai_id and photo_id:
        url = f"https://www.kwai.com/@{kwai_id}/video/{photo_id}"
        url_perfil = f"https://www.kwai.com/@{kwai_id}"
    elif user_clean and photo_id:
        url = f"https://www.kwai.com/{user_clean}/video/{photo_id}"
        url_perfil = f"https://www.kwai.com/{user_clean}"
    elif keyword:
        url = f"https://www.kwai.com/explore/{quote(keyword)}"
        url_perfil = None
    else:
        url = "https://www.kwai.com/"
        url_perfil = None

    texto_bruto = feed.get("caption") or feed.get("title")
    texto = html.unescape(texto_bruto) if texto_bruto else None

    return {
        "id": photo_id,
        "url": url,
        "autor": {
            "usuario": _str_ou_none(feed.get("user_name")),
            "id": _str_ou_none(feed.get("user_id_str") or feed.get("user_id")),
            "url_perfil": url_perfil,
        },
        "texto": texto,
        "data_publicacao": _normalizar_data(feed.get("timestamp")),
        "engajamento": {
            "curtidas": feed.get("like_count", 0),
            "comentarios": feed.get("comment_count", 0),
            "compartilhamentos": feed.get("forward_count", feed.get("share_count", 0)),
            "visualizacoes": feed.get("view_count", 0),
        },
        "coletado_em": _agora_iso(),
    }


def _montar_comentario(c, postagem_url):
    """Monta um objeto Comentario a partir de um item da API do Kwai."""
    return {
        "id": _str_ou_none(c.get("comment_id")),
        "postagem_url": postagem_url,
        "autor": {
            "usuario": _str_ou_none(c.get("author_name") or c.get("user_name")),
            "id": _str_ou_none(c.get("author_id") or c.get("user_id")),
        },
        "texto": c.get("content") or "",
        "curtidas": c.get("like_count", 0),
        "data": _normalizar_data(c.get("timestamp") or c.get("created_at")),
        "coletado_em": _agora_iso(),
    }


def _extrair_feeds_do_nuxt(page):
    """Extrai feeds do window.__NUXT__ de forma defensiva. Retorna [] se malformado."""
    try:
        nuxt = page.evaluate("() => window.__NUXT__")
        return nuxt["data"][0]["feedsData"]["feeds"]
    except (KeyError, IndexError, TypeError):
        return []


# ------------------------------------------------------------
# Funcionalidade 1 — Busca por palavra-chave
# ------------------------------------------------------------

def buscar_palavra_chave(keyword, limit, output):
    """Busca postagens por palavra-chave via interceptação XHR."""
    print(f"Buscando '{keyword}' (limite: {limit})")

    feeds = []
    ids_vistos = set()

    with sync_playwright() as p:
        browser, context, page = _abrir_contexto(p)

        def capturar(response):
            if "outer" in response.url and response.request.resource_type in ["xhr", "fetch"]:
                try:
                    data = response.json()
                    if isinstance(data, dict) and "feeds" in data:
                        print(f"Capturados {len(data['feeds'])} vídeos.")
                        feeds.extend(data["feeds"])
                except Exception:
                    pass

        page.on("response", capturar)

        try:
            page.goto(f"https://www.kwai.com/explore/{quote(keyword)}",
                      timeout=CONFIG["goto_timeout"])
            page.wait_for_timeout(CONFIG["wait_after_load"])

            postagens = []
            for feed in feeds:
                if len(postagens) >= limit:
                    break
                post = _montar_postagem(feed, keyword=keyword)
                if post["id"] and post["id"] not in ids_vistos:
                    ids_vistos.add(post["id"])
                    postagens.append(post)
        except Exception as e:
            print(f"Erro na busca: {e}")
            postagens = []
        finally:
            browser.close()

    salvar_json(postagens, output)


# ------------------------------------------------------------
# Funcionalidade 2 — Postagens de um usuário
# ------------------------------------------------------------

def buscar_usuario(user, limit, output):
    """
    Busca postagens de um usuário.
    Primeira leva vem do SSR (window.__NUXT__); as seguintes via XHR ao rolar.
    """
    print(f"Buscando postagens de '{user}' (limite: {limit})")

    dados = []
    ids_vistos = set()
    pendentes = []

    user_clean = user if user.startswith("@") else f"@{user}"

    with sync_playwright() as p:
        browser, context, page = _abrir_contexto(p)

        def capturar_paginacao(response):
            if response.request.resource_type in ["xhr", "fetch"]:
                try:
                    data = response.json()
                    if isinstance(data, dict) and "feeds" in data:
                        pendentes.extend(data["feeds"])
                except Exception:
                    pass

        page.on("response", capturar_paginacao)

        try:
            page.goto(f"https://www.kwai.com/{user_clean}", timeout=CONFIG["goto_timeout"])
            page.wait_for_timeout(4000)

            feeds_ssr = _extrair_feeds_do_nuxt(page)
            print(f"{len(feeds_ssr)} vídeos via SSR.")

            for feed in feeds_ssr:
                post = _montar_postagem(feed, user_clean=user_clean)
                if post["id"] and post["id"] not in ids_vistos:
                    ids_vistos.add(post["id"])
                    dados.append(post)

            # Paginação por scroll
            tentativas_vazias = 0
            while len(dados) < limit and tentativas_vazias < 4:
                page.mouse.wheel(0, 3000)
                page.wait_for_timeout(CONFIG["scroll_wait"])

                novos = 0
                while pendentes:
                    feed = pendentes.pop(0)
                    post = _montar_postagem(feed, user_clean=user_clean)
                    if post["id"] and post["id"] not in ids_vistos:
                        ids_vistos.add(post["id"])
                        dados.append(post)
                        novos += 1

                tentativas_vazias = tentativas_vazias + 1 if novos == 0 else 0

            dados = dados[:limit]
        except Exception as e:
            print(f"Erro ao acessar perfil: {e}")
        finally:
            browser.close()

    salvar_json(dados, output)


# ------------------------------------------------------------
# Funcionalidade 3 — Comentários de uma postagem
# ------------------------------------------------------------

def buscar_comentarios(url, output):
    """
    Busca comentários de uma postagem.

    Observação: o endpoint getComments/list exige sessão autenticada.
    Sem login, o Kwai responde com result:11 (erro de rede). Este bloco
    captura os comentários quando disponíveis e devolve [] caso contrário.
    """
    if not url or "kwai.com" not in url:
        print("URL inválida.")
        return

    print(f"Buscando comentários: {url}")

    capturados = []

    with sync_playwright() as p:
        browser, context, page = _abrir_contexto(p)

        def capturar(response):
            if "getComments/list" in response.url:
                try:
                    data = response.json()
                    lista = data.get("comments") or (data.get("data") or {}).get("comments")
                    if isinstance(lista, list):
                        capturados.extend(lista)
                except Exception:
                    pass

        page.on("response", capturar)

        try:
            page.goto(url, timeout=CONFIG["goto_timeout"])
            page.wait_for_timeout(4000)

            for _ in range(4):
                page.evaluate("window.scrollBy(0, 800)")
                page.wait_for_timeout(CONFIG["scroll_wait"])

            comentarios = [_montar_comentario(c, postagem_url=url) for c in capturados]
        except Exception as e:
            print(f"Erro ao acessar postagem: {e}")
            comentarios = []
        finally:
            browser.close()

    if not comentarios:
        print("Nenhum comentário capturado (o Kwai pode exigir sessão autenticada).")

    salvar_json(comentarios, output)


# ------------------------------------------------------------
# CLI
# ------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="VoxRadar — Kwai Collector (A1_Radar)")
    sub = parser.add_subparsers(dest="comando", required=True)

    p1 = sub.add_parser("busca", help="Postagens por palavra-chave")
    p1.add_argument("--keyword", required=True)
    p1.add_argument("--limit", type=int, default=50)
    p1.add_argument("--out", required=True)

    p2 = sub.add_parser("usuario", help="Postagens de um perfil")
    p2.add_argument("--user", required=True)
    p2.add_argument("--limit", type=int, default=100)
    p2.add_argument("--out", required=True)

    p3 = sub.add_parser("comentarios", help="Comentários de uma postagem")
    p3.add_argument("--url", required=True)
    p3.add_argument("--out", required=True)

    args = parser.parse_args()

    if args.comando == "busca":
        buscar_palavra_chave(args.keyword, args.limit, args.out)
    elif args.comando == "usuario":
        buscar_usuario(args.user, args.limit, args.out)
    elif args.comando == "comentarios":
        buscar_comentarios(args.url, args.out)


if __name__ == "__main__":
    main()
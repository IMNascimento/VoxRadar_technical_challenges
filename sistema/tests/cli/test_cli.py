import json
from pathlib import Path

import pytest

from kwai_collector import __main__ as cli
from kwai_collector import midia, mobile_client, web_client
from kwai_collector.errors import CollectorError, NetworkError, Sig3ServiceUnavailableError


@pytest.fixture(autouse=True)
def cwd_temporario(tmp_path, monkeypatch):
    """A CLI grava em ./out relativo ao cwd -- isola cada teste."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


def postagem(pid="1", url=None, **extra):
    p = {"id": pid, "url": url or f"https://www.kwai.com/@u/video/{pid}", "midia": {}}
    p.update(extra)
    return p


def le(path):
    return json.loads(path.read_text(encoding="utf-8"))


# --- helpers ------------------------------------------------------------

@pytest.mark.parametrize(
    "entrada,esperado",
    [
        ("@perfil", "perfil"),
        ("  futebol  brasil ", "futebol_brasil"),
        ("a/b\\c:d*e", "abcde"),
        ("ção", "o"),
        ("a.b-c_d", "a.b-c_d"),
        ("", "saida"),
        ("@@", "saida"),
        ("!!!", "saida"),
    ],
)
def test_slug(entrada, esperado):
    assert cli._slug(entrada) == esperado


def test_gravar_json_cria_pastas_e_preserva_unicode(tmp_path):
    destino = tmp_path / "a" / "b" / "x.json"
    cli._gravar_json({"t": "ção"}, destino)
    assert "ção" in destino.read_text(encoding="utf-8")  # ensure_ascii=False
    assert le(destino) == {"t": "ção"}


def test_escrever_saida_imprime_contagem(tmp_path, capsys):
    cli._escrever_saida([1, 2], str(tmp_path / "o.json"))
    assert "[ok] 2 item(ns) salvo(s)" in capsys.readouterr().out


def test_comentarios_melhor_esforco_engole_collector_error(monkeypatch, capsys):
    def falha(*a, **k):
        raise Sig3ServiceUnavailableError("sem servico")

    monkeypatch.setattr(mobile_client, "comentarios_de_postagem", falha)
    assert cli._coletar_comentarios_melhor_esforco("u", 5) is None
    assert "sem servico" in capsys.readouterr().err


def test_comentarios_melhor_esforco_repassa_argumentos(monkeypatch):
    visto = {}

    def fake(url, limit, incluir_subcomentarios):
        visto.update(url=url, limit=limit, sub=incluir_subcomentarios)
        return ["c"]

    monkeypatch.setattr(mobile_client, "comentarios_de_postagem", fake)
    assert cli._coletar_comentarios_melhor_esforco("u", 7, com_subcomentarios=True) == ["c"]
    assert visto == {"url": "u", "limit": 7, "sub": True}


# --- parser -------------------------------------------------------------

def test_parser_exige_subcomando():
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args([])


@pytest.mark.parametrize(
    "argv",
    [["busca"], ["usuario"], ["comentarios", "--url", "x"], ["comentarios", "--out", "x"]],
)
def test_parser_argumentos_obrigatorios(argv):
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(argv)


def test_parser_defaults_busca():
    a = cli.build_parser().parse_args(["busca", "--keyword", "x"])
    assert (a.limit, a.sem_comentarios, a.baixar_midia, a.com_subcomentarios) == (50, False, False, False)
    assert a.func is cli.cmd_busca


def test_parser_defaults_usuario():
    a = cli.build_parser().parse_args(["usuario", "--user", "@u"])
    assert a.limit == 50 and a.out is None and a.comentarios_limit == 50
    assert not (a.perfil or a.comentarios or a.baixar_midia or a.com_subcomentarios)
    assert a.func is cli.cmd_usuario


def test_parser_comentarios():
    a = cli.build_parser().parse_args(["comentarios", "--url", "u", "--out", "o.json", "--limit", "3"])
    assert (a.url, a.out, a.limit) == ("u", "o.json", 3)
    assert a.func is cli.cmd_comentarios


# --- main: codigos de saida e tratamento de erro ----------------------------

def test_main_sucesso_devolve_codigo_da_funcao(monkeypatch):
    monkeypatch.setattr(web_client, "buscar_por_palavra_chave", lambda k, limit: [])
    assert cli.main(["busca", "--keyword", "x", "--sem-comentarios"]) == 0


def test_main_collector_error_vira_exit_1_com_mensagem(monkeypatch, capsys):
    def falha(*a, **k):
        raise NetworkError("sem internet")

    monkeypatch.setattr(web_client, "buscar_por_palavra_chave", falha)
    assert cli.main(["busca", "--keyword", "x"]) == 1
    assert "[erro] sem internet" in capsys.readouterr().err


def test_main_erro_inesperado_nao_gera_traceback(monkeypatch, capsys):
    def falha(*a, **k):
        raise KeyError("boom")

    monkeypatch.setattr(web_client, "buscar_por_palavra_chave", falha)
    assert cli.main(["busca", "--keyword", "x"]) == 1
    err = capsys.readouterr().err
    assert "[erro inesperado] KeyError" in err
    assert "Traceback" not in err


def test_main_ctrl_c_devolve_130(monkeypatch, capsys):
    def falha(*a, **k):
        raise KeyboardInterrupt

    monkeypatch.setattr(web_client, "buscar_por_palavra_chave", falha)
    assert cli.main(["busca", "--keyword", "x"]) == 130
    assert "cancelado" in capsys.readouterr().err


# --- cmd_busca ----------------------------------------------------------

def test_busca_grava_postagem_e_comentarios(monkeypatch, cwd_temporario):
    monkeypatch.setattr(web_client, "buscar_por_palavra_chave", lambda k, limit: [postagem("1"), postagem("2")])
    monkeypatch.setattr(mobile_client, "comentarios_de_postagem", lambda url, limit, incluir_subcomentarios: [{"id": "c"}])

    assert cli.main(["busca", "--keyword", "Futebol Brasil"]) == 0

    raiz = cwd_temporario / "out" / "Futebol_Brasil"
    assert le(raiz / "1" / "postagem.json")["id"] == "1"
    assert le(raiz / "2" / "comentarios.json") == [{"id": "c"}]


def test_busca_sem_comentarios_nao_chama_mobile(monkeypatch, cwd_temporario):
    monkeypatch.setattr(web_client, "buscar_por_palavra_chave", lambda k, limit: [postagem("1")])

    def nao_deve(*a, **k):
        raise AssertionError("mobile nao deveria ser chamado")

    monkeypatch.setattr(mobile_client, "comentarios_de_postagem", nao_deve)
    assert cli.main(["busca", "--keyword", "x", "--sem-comentarios"]) == 0
    assert not (cwd_temporario / "out" / "x" / "1" / "comentarios.json").exists()


def test_busca_comentarios_indisponiveis_nao_impedem_postagem(monkeypatch, cwd_temporario, capsys):
    monkeypatch.setattr(web_client, "buscar_por_palavra_chave", lambda k, limit: [postagem("1")])

    def falha(*a, **k):
        raise Sig3ServiceUnavailableError("fora")

    monkeypatch.setattr(mobile_client, "comentarios_de_postagem", falha)
    assert cli.main(["busca", "--keyword", "x"]) == 0

    pasta = cwd_temporario / "out" / "x" / "1"
    assert (pasta / "postagem.json").exists()
    assert not (pasta / "comentarios.json").exists()
    assert "[aviso]" in capsys.readouterr().err


def test_busca_pula_postagem_sem_id(monkeypatch, cwd_temporario, capsys):
    monkeypatch.setattr(web_client, "buscar_por_palavra_chave", lambda k, limit: [postagem(None)])
    assert cli.main(["busca", "--keyword", "x", "--sem-comentarios"]) == 0
    assert "sem id" in capsys.readouterr().err
    assert not (cwd_temporario / "out").exists()


def test_busca_baixar_midia_e_propaga_limit(monkeypatch, cwd_temporario):
    visto = {}

    def buscar(k, limit):
        visto["limit"] = limit
        return [postagem("1")]

    baixadas = []
    monkeypatch.setattr(web_client, "buscar_por_palavra_chave", buscar)
    monkeypatch.setattr(midia, "baixar_midia", lambda p, pasta: baixadas.append((p["id"], pasta)))

    assert cli.main(["busca", "--keyword", "x", "--sem-comentarios", "--baixar-midia", "--limit", "3"]) == 0
    assert visto["limit"] == 3
    assert baixadas == [("1", Path("out") / "x" / "1")]  # caminho relativo ao cwd


# --- cmd_usuario --------------------------------------------------------

def test_usuario_grava_lista_em_out_usuario_json(monkeypatch, cwd_temporario):
    monkeypatch.setattr(web_client, "carregar_perfil", lambda user, limit: (None, [postagem("1"), postagem("2")]))
    assert cli.main(["usuario", "--user", "@fulano", "--limit", "2"]) == 0
    assert [p["id"] for p in le(cwd_temporario / "out" / "fulano" / "usuario.json")] == ["1", "2"]


def test_usuario_out_customizado(monkeypatch, cwd_temporario):
    monkeypatch.setattr(web_client, "carregar_perfil", lambda user, limit: (None, [postagem("1")]))
    assert cli.main(["usuario", "--user", "fulano", "--out", "meu/arquivo.json"]) == 0
    assert (cwd_temporario / "meu" / "arquivo.json").exists()
    assert not (cwd_temporario / "out").exists()


def test_usuario_avisa_quando_vem_menos_que_o_limite(monkeypatch, capsys):
    monkeypatch.setattr(web_client, "carregar_perfil", lambda user, limit: (None, [postagem("1")]))
    cli.main(["usuario", "--user", "fulano", "--limit", "5"])
    assert "menos que o limite pedido (5)" in capsys.readouterr().out


def test_usuario_sem_aviso_quando_atinge_o_limite(monkeypatch, capsys):
    monkeypatch.setattr(web_client, "carregar_perfil", lambda user, limit: (None, [postagem("1")]))
    cli.main(["usuario", "--user", "fulano", "--limit", "1"])
    assert "menos que o limite" not in capsys.readouterr().out


def test_usuario_perfil_gravado(monkeypatch, cwd_temporario):
    monkeypatch.setattr(web_client, "carregar_perfil", lambda user, limit: ({"usuario": "@fulano"}, []))
    assert cli.main(["usuario", "--user", "fulano", "--perfil"]) == 0
    assert le(cwd_temporario / "out" / "fulano" / "perfil.json") == {"usuario": "@fulano"}


def test_usuario_perfil_indisponivel_avisa(monkeypatch, cwd_temporario, capsys):
    monkeypatch.setattr(web_client, "carregar_perfil", lambda user, limit: (None, []))
    assert cli.main(["usuario", "--user", "fulano", "--perfil"]) == 0
    assert "nao foi possivel coletar dados de perfil" in capsys.readouterr().err
    assert not (cwd_temporario / "out" / "fulano" / "perfil.json").exists()


def test_usuario_handle_invalido_da_exit_1(capsys):
    assert cli.main(["usuario", "--user", "com espaco"]) == 1
    assert "[erro]" in capsys.readouterr().err


def test_usuario_comentarios_por_postagem_com_limite_proprio(monkeypatch, cwd_temporario):
    monkeypatch.setattr(web_client, "carregar_perfil", lambda user, limit: (None, [postagem("1")]))
    visto = {}

    def comentarios(url, limit, incluir_subcomentarios):
        visto.update(limit=limit, sub=incluir_subcomentarios)
        return [{"id": "c"}]

    monkeypatch.setattr(mobile_client, "comentarios_de_postagem", comentarios)
    assert cli.main(["usuario", "--user", "u", "--comentarios", "--comentarios-limit", "9", "--com-subcomentarios"]) == 0

    pasta = cwd_temporario / "out" / "u" / "1"
    assert le(pasta / "comentarios.json") == [{"id": "c"}]
    assert (pasta / "postagem.json").exists()
    assert visto == {"limit": 9, "sub": True}


def test_usuario_sem_flags_extras_nao_cria_pastas_por_video(monkeypatch, cwd_temporario):
    monkeypatch.setattr(web_client, "carregar_perfil", lambda user, limit: (None, [postagem("1")]))
    assert cli.main(["usuario", "--user", "u"]) == 0
    assert sorted(p.name for p in (cwd_temporario / "out" / "u").iterdir()) == ["usuario.json"]


# --- cmd_comentarios ----------------------------------------------------

def test_comentarios_grava_no_out(monkeypatch, cwd_temporario):
    visto = {}

    def fake(url, limit, incluir_subcomentarios):
        visto.update(url=url, limit=limit, sub=incluir_subcomentarios)
        return [{"id": "c1"}, {"id": "c2"}]

    monkeypatch.setattr(mobile_client, "comentarios_de_postagem", fake)
    assert cli.main(["comentarios", "--url", "https://x/video/1", "--out", "c.json", "--limit", "4"]) == 0
    assert le(cwd_temporario / "c.json") == [{"id": "c1"}, {"id": "c2"}]
    assert visto == {"url": "https://x/video/1", "limit": 4, "sub": False}


def test_comentarios_erro_do_coletor_nao_cria_arquivo(monkeypatch, cwd_temporario, capsys):
    def falha(*a, **k):
        raise Sig3ServiceUnavailableError("servico fora do ar")

    monkeypatch.setattr(mobile_client, "comentarios_de_postagem", falha)
    assert cli.main(["comentarios", "--url", "https://x/video/1", "--out", "c.json"]) == 1
    assert "servico fora do ar" in capsys.readouterr().err
    assert not (cwd_temporario / "c.json").exists()


def test_comentarios_url_sem_video_id_da_exit_1(cwd_temporario, capsys):
    assert cli.main(["comentarios", "--url", "https://www.kwai.com/@x", "--out", "c.json"]) == 1
    assert "photo_id" in capsys.readouterr().err

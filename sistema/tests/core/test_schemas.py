from datetime import datetime

from kwai_collector import schemas


def test_now_iso_formato_utc_com_z():
    valor = schemas.now_iso()
    assert valor.endswith("Z")
    datetime.strptime(valor, "%Y-%m-%dT%H:%M:%SZ")


def test_ms_timestamp_to_iso_converte_milissegundos():
    assert schemas.ms_timestamp_to_iso(1_700_000_000_000) == "2023-11-14T22:13:20Z"


def test_ms_timestamp_to_iso_aceita_zero_como_epoch():
    assert schemas.ms_timestamp_to_iso(0) == "1970-01-01T00:00:00Z"


def test_ms_timestamp_to_iso_none_e_invalidos_viram_none():
    assert schemas.ms_timestamp_to_iso(None) is None
    assert schemas.ms_timestamp_to_iso(10 ** 30) is None


def test_build_postagem_estrutura_do_schema():
    p = schemas.build_postagem(
        id_="1", url="https://x/1", autor_usuario="@a", autor_id="9",
        autor_url_perfil="https://x/@a", texto="oi", data_publicacao="2024-01-01T00:00:00Z",
        curtidas=1, comentarios=2, compartilhamentos=3, visualizacoes=4,
        video_url="v", thumbnail_url="t",
    )
    assert set(p) == {"id", "url", "autor", "texto", "data_publicacao", "engajamento", "midia", "coletado_em"}
    assert p["autor"] == {"usuario": "@a", "id": "9", "url_perfil": "https://x/@a"}
    assert p["engajamento"] == {"curtidas": 1, "comentarios": 2, "compartilhamentos": 3, "visualizacoes": 4}
    assert p["midia"] == {"video_url": "v", "thumbnail_url": "t"}


def test_build_postagem_nao_inventa_valores_ausentes():
    p = schemas.build_postagem(
        id_=None, url="u", autor_usuario=None, autor_id=None, autor_url_perfil=None,
        texto=None, data_publicacao=None, curtidas=None, comentarios=None,
        compartilhamentos=None, visualizacoes=None,
    )
    assert p["engajamento"] == dict.fromkeys(["curtidas", "comentarios", "compartilhamentos", "visualizacoes"])
    assert p["midia"] == {"video_url": None, "thumbnail_url": None}
    assert p["texto"] is None


def test_build_perfil_campos():
    p = schemas.build_perfil(
        usuario="@a", id_="1", nome="A", bio="b", verificado=True, avatar_url="u",
        seguidores=1, seguindo=2, total_postagens=3, url_perfil="https://x/@a",
    )
    assert p["verificado"] is True
    assert (p["seguidores"], p["seguindo"], p["total_postagens"]) == (1, 2, 3)
    assert p["coletado_em"].endswith("Z")


def test_build_comentario_respondendo_a_default_none():
    c = schemas.build_comentario(
        id_="1", postagem_url="u", autor_usuario="x", autor_id="2", texto="t", curtidas=0, data=None,
    )
    assert c["respondendo_a"] is None
    assert c["autor"] == {"usuario": "x", "id": "2"}
    assert c["curtidas"] == 0  # 0 real nao vira None


def test_build_comentario_sub_comentario():
    c = schemas.build_comentario(
        id_="1", postagem_url="u", autor_usuario=None, autor_id=None, texto="", curtidas=None,
        data=None, respondendo_a="99",
    )
    assert c["respondendo_a"] == "99"

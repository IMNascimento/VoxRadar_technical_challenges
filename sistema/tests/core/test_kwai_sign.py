import hashlib

import pytest

from kwai_collector import kwai_sign


def test_rotacoes_de_32_bits():
    assert kwai_sign._rotl32(0x80000000, 1) == 1
    assert kwai_sign._rotr32(1, 1) == 0x80000000
    assert kwai_sign._rotl32(0x12345678, 8) == 0x34567812
    assert kwai_sign._rotr32(kwai_sign._rotl32(0xDEADBEEF, 7), 7) == 0xDEADBEEF


def test_chave_cold_e_o_package_name_do_app():
    # Documentado em kwai_sign.py: a chave da 1a chamada decodifica como o
    # package name do app. Serve de teste de regressao da cifra inteira.
    assert kwai_sign.get_key(warm=False) == b"com.kwai.video"


def test_chave_warm_e_estavel_e_diferente_da_cold():
    warm = kwai_sign.get_key(warm=True)
    assert warm == kwai_sign.get_key(warm=True)
    assert warm != kwai_sign.get_key(warm=False)
    assert 0 < len(warm) <= 16
    assert b"\x00" not in warm


def test_trim_cstring():
    assert kwai_sign._trim_cstring(b"abc\x00def") == b"abc"
    assert kwai_sign._trim_cstring(b"x" * 20) == b"x" * 16
    assert kwai_sign._trim_cstring(b"\x00abc") == b""


def test_build_sig_input_ordena_e_concatena_sem_separador():
    assert kwai_sign.build_sig_input({"b": "2", "a": "1", "c": "3"}) == b"a=1b=2c=3"


def test_build_sig_input_utf8():
    assert kwai_sign.build_sig_input({"k": "ção"}) == "k=ção".encode("utf-8")


def test_compute_sig_e_md5_de_input_mais_chave():
    params = {"b": "2", "a": "1"}
    esperado = hashlib.md5(b"a=1b=2" + kwai_sign.get_key(warm=True)).hexdigest()
    assert kwai_sign.compute_sig(params) == esperado
    assert kwai_sign.compute_sig(params) == kwai_sign.compute_sig({"a": "1", "b": "2"})


def test_compute_sig_cold_difere_de_warm():
    assert kwai_sign.compute_sig({"a": "1"}, warm=False) != kwai_sign.compute_sig({"a": "1"}, warm=True)


def test_compute_sig_muda_com_os_params():
    assert kwai_sign.compute_sig({"a": "1"}) != kwai_sign.compute_sig({"a": "2"})


def test_resign_remove_campos_de_saida_e_mantem_client_key():
    query = {"q": "1", "__NS_sig3": "x", "__NS_sig4": "y", "__NStokensig": "z"}
    body = {"b": "2", "sig": "velha", "client_key": "abc"}
    esperado = kwai_sign.compute_sig({"q": "1", "b": "2", "client_key": "abc"})
    assert kwai_sign.resign(query, body) == esperado


def test_resign_usa_client_key_padrao_quando_ausente():
    assert kwai_sign.resign({}, {"b": "2"}) == kwai_sign.compute_sig({"b": "2", "client_key": "3c2cd3f3"})


@pytest.mark.parametrize("arquivo,tamanho", [("buf14.bin", 32), ("keyindex_pos.bin", 224)])
def test_tabelas_embutidas_tem_tamanho_esperado(arquivo, tamanho):
    assert (kwai_sign._ASM_DIR / arquivo).stat().st_size == tamanho

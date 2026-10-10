from kwai_collector.security.native_signature_boundary import (
    preparar_entrada_nativa,
)


def test_canonicalizacao_ordena_e_concatena_sem_separador():
    resultado = preparar_entrada_nativa(
        query={
            "z": "3",
            "a": "1",
        },
        body={
            "m": "2",
        },
    )

    assert resultado.canonical_text == ("a=1m=2z=3")


def test_canonical_bytes_sao_utf8():
    resultado = preparar_entrada_nativa(
        query={
            "texto": "olá",
        },
        body={},
    )

    assert resultado.canonical_bytes == ("texto=olá".encode())


def test_body_prevalece_sobre_query():
    resultado = preparar_entrada_nativa(
        query={
            "photo_id": "query",
            "teste": "1",
        },
        body={
            "photo_id": "body",
        },
    )

    assert resultado.params == {
        "photo_id": "body",
        "teste": "1",
    }

    assert resultado.canonical_text == ("photo_id=bodyphoto_id=queryteste=1")


def test_canonicalizacao_preserva_duplicatas_e_valores_vazios():
    resultado = preparar_entrada_nativa(
        query={
            "duplicada": "query",
            "vazia": None,
        },
        body={
            "duplicada": "body",
            "vazia": "",
        },
    )

    esperado = "duplicada=bodyduplicada=queryvazia=vazia="

    assert resultado.params == {
        "duplicada": "body",
        "vazia": "",
    }
    assert resultado.canonical_text == esperado
    assert resultado.canonical_bytes == esperado.encode("utf-8")


def test_client_salt_participa_da_canonicalizacao():
    resultado = preparar_entrada_nativa(
        query={
            "client_salt": "abc",
            "a": "1",
        },
        body={},
    )

    assert resultado.params == {
        "client_salt": "abc",
        "a": "1",
    }

    assert resultado.canonical_text == ("a=1client_salt=abc")


def test_none_vira_string_vazia():
    resultado = preparar_entrada_nativa(
        query={
            "a": None,
        },
        body={},
    )

    assert resultado.params == {
        "a": "",
    }

    assert resultado.canonical_text == "a="

from kwai_collector.security.mock_signer_engine import (
    MockSignerEngine,
)


def gerar_token(
    signer: MockSignerEngine,
    photo_id: str,
) -> str:
    resultado = signer.sign(
        query={
            "did": "did_teste",
        },
        body={
            "photo_id": photo_id,
        },
        client_salt="salt_teste",
    )

    return resultado["__MOCK_NS_sig3"]


def test_mock_signer_retorna_token_deterministico():
    signer = MockSignerEngine()

    primeiro = gerar_token(
        signer,
        "123",
    )

    segundo = gerar_token(
        signer,
        "123",
    )

    assert primeiro == segundo
    assert len(primeiro) == 32

    int(primeiro, 16)


def test_mock_signer_muda_com_entrada():
    signer = MockSignerEngine()

    primeiro = gerar_token(
        signer,
        "123",
    )

    segundo = gerar_token(
        signer,
        "456",
    )

    assert primeiro != segundo


def test_mock_signer_muda_com_secret():
    primeiro_signer = MockSignerEngine(
        secret="segredo_a",
    )

    segundo_signer = MockSignerEngine(
        secret="segredo_b",
    )

    primeiro = gerar_token(
        primeiro_signer,
        "123",
    )

    segundo = gerar_token(
        segundo_signer,
        "123",
    )

    assert primeiro != segundo

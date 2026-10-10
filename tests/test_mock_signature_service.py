from kwai_collector.security.mock_signature_service import (
    MockSignatureService,
)


def test_normalize_ordena_parametros():
    params = {
        "photo_id": "123",
        "count": "10",
        "pcursor": "",
    }

    resultado = MockSignatureService.normalize(params)

    assert resultado == "count=10&pcursor=&photo_id=123"


def test_generate_sig3_retorna_32_hex():
    service = MockSignatureService()

    query = {
        "did": "did_teste",
        "appver": "1.0",
    }

    body = {
        "photo_id": "123",
        "count": "10",
    }

    token = service.generate_sig3(
        query=query,
        body=body,
    )

    assert len(token) == 32

    int(token, 16)


def test_body_prevalece_em_chave_duplicada():
    service = MockSignatureService()

    query = {
        "count": "5",
        "did": "did_teste",
    }

    body = {
        "count": "10",
        "photo_id": "123",
    }

    combinado = dict(query)
    combinado.update(body)

    normalizado = service.normalize(combinado)

    assert "count=10" in normalizado
    assert "count=5" not in normalizado


def test_generate_sig3_e_deterministico():
    service = MockSignatureService()

    query = {
        "did": "did_teste",
    }

    body = {
        "photo_id": "123",
    }

    primeiro = service.generate_sig3(
        query=query,
        body=body,
    )

    segundo = service.generate_sig3(
        query=query,
        body=body,
    )

    assert primeiro == segundo

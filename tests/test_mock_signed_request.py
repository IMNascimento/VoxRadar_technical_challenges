from kwai_collector.security.mock_signed_request import (
    preparar_requisicao_mock_assinada,
)


def test_mock_signed_request_fluxo_completo():
    query = {
        "did": "did_teste",
        "count": "5",
        "lat": "-20.0",
        "lon": "-43.0",
        "client_salt": "salt_teste",
        "valor_none": None,
    }

    body = {
        "photo_id": "123456789",
        "count": "10",
        "pcursor": "",
    }

    resultado = preparar_requisicao_mock_assinada(
        query=query,
        body=body,
    )

    assert "lat" not in resultado.query
    assert "lon" not in resultado.query

    assert resultado.client_salt == "salt_teste"

    assert "client_salt" not in resultado.query

    assert "client_salt" not in resultado.body

    assert "count" not in resultado.query

    assert resultado.body["count"] == "10"

    assert resultado.query["valor_none"] == ""

    assert len(resultado.mock_sig3) == 32

    int(
        resultado.mock_sig3,
        16,
    )


def test_mock_signed_request_e_deterministico():
    query = {
        "did": "did_teste",
    }

    body = {
        "photo_id": "123",
    }

    primeiro = preparar_requisicao_mock_assinada(
        query=query,
        body=body,
    )

    segundo = preparar_requisicao_mock_assinada(
        query=query,
        body=body,
    )

    assert primeiro.mock_sig3 == segundo.mock_sig3


def test_body_prevalece_na_requisicao_mock():
    query = {
        "count": "5",
        "did": "did_teste",
    }

    body = {
        "count": "20",
        "photo_id": "123",
    }

    resultado = preparar_requisicao_mock_assinada(
        query=query,
        body=body,
    )

    assert "count" not in resultado.query
    assert resultado.body["count"] == "20"

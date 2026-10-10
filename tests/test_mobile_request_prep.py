from kwai_collector.security.mobile_request_prep import (
    preparar_requisicao_mobile,
)


def test_body_deve_prevalecer_sobre_query() -> None:
    resultado = preparar_requisicao_mobile(
        query={
            "photo_id": "111",
            "count": "10",
        },
        body={
            "photo_id": "222",
        },
    )

    assert "photo_id" not in resultado.query

    assert resultado.body["photo_id"] == "222"


def test_deve_remover_lat_lon() -> None:
    resultado = preparar_requisicao_mobile(
        query={
            "lat": "-10.0",
            "lon": "-40.0",
            "count": "10",
        },
        body={},
    )

    assert "lat" not in resultado.query
    assert "lon" not in resultado.query

    assert resultado.query["count"] == "10"


def test_deve_separar_client_salt() -> None:
    resultado = preparar_requisicao_mobile(
        query={},
        body={
            "client_salt": "TESTE",
            "photo_id": "123",
        },
    )

    assert resultado.client_salt == "TESTE"

    assert "client_salt" not in resultado.body


def test_none_deve_virar_string_vazia() -> None:
    resultado = preparar_requisicao_mobile(
        query={
            "pcursor": None,
        },
        body={},
    )

    assert resultado.query["pcursor"] == ""

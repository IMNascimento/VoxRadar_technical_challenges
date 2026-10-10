"""A1_Radar."""

import logging
from typing import Any, Protocol

import httpx

from kwai_collector.cli_builders import (
    montar_mobile_session_params,
)
from kwai_collector.clients.comment_client import (
    KwaiCommentsError,
)
from kwai_collector.clients.mobile_comment_client import (
    build_root_payload,
    get_comment_id,
    get_pcursor,
    get_root_comments,
    is_end_cursor,
)

logger = logging.getLogger(__name__)


MOBILE_BASE_URLS = (
    "https://api.kwai-pro.com",
    "https://api.kwaipros.com",
)

MOBILE_COMMENTS_ENDPOINT = "/rest/o/comment/list/v2"

DEFAULT_TIMEOUT = 20.0

# Pelo fluxo que vocês observaram,
# cada página retorna no máximo 20 comentários.
ROOT_PAGE_SIZE = 20


MOBILE_HEADERS = {
    "Accept": ("application/json, text/plain, */*"),
    "Content-Type": ("application/x-www-form-urlencoded"),
    "User-Agent": (
        "Mozilla/5.0 "
        "(Linux; Android 14; SM-A356E) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/152.0.0.0 "
        "Mobile Safari/537.36"
    ),
}


class MobileRequestSigner(Protocol):
    """
    Interface utilizada pelo cliente HTTP.

    A implementação real pode utilizar uma fonte
    autorizada de assinatura.

    O cliente HTTP não precisa saber como as
    assinaturas são produzidas.
    """

    def sign(
        self,
        *,
        query_params: dict[str, str],
        body: dict[str, str],
    ) -> tuple[str, str]:
        """
        Retorna:

            (
                sig,
                __NS_sig3,
            )
        """
        ...


def _montar_mobile_headers() -> dict[str, str]:
    """
    Retorna uma cópia dos headers utilizados
    no fluxo HTTP mobile.
    """
    return dict(MOBILE_HEADERS)


def _params_seguros(
    params: dict[str, str],
) -> dict[str, str]:
    """
    Remove valores sensíveis dos logs.
    """
    campos_sensiveis = {
        "did",
        "egid",
        "sig",
        "sig2",
        "__ns_sig3",
        "__ns_sig4",
        "client_key",
        "client_salt",
        "session_id",
        "llsid",
        "ud",
        "oc",
    }

    return {
        chave: ("***REDACTED***" if chave.lower() in campos_sensiveis else valor)
        for chave, valor in params.items()
    }


def _registrar_request(
    url: str,
    query_params: dict[str, str],
    body: dict[str, str],
) -> None:
    """
    Registra somente informações seguras
    sobre a request.
    """
    params = _params_seguros(query_params)

    request = httpx.Request(
        "POST",
        url,
        params=params,
    )

    logger.debug(
        "MOBILE REQUEST | url=%s",
        request.url,
    )

    logger.debug(
        "MOBILE REQUEST | query_keys=%s",
        sorted(query_params.keys()),
    )

    logger.debug(
        "MOBILE REQUEST | body_keys=%s",
        sorted(body.keys()),
    )

    logger.debug(
        "MOBILE REQUEST | pcursor=%s",
        ("preenchido" if body.get("pcursor") else "vazio"),
    )

    logger.debug(
        "MOBILE REQUEST | llsid=%s",
        ("preenchido" if body.get("llsid") else "vazio"),
    )

    logger.debug(
        "MOBILE REQUEST | count=%r",
        body.get("count"),
    )

    logger.debug(
        "MOBILE REQUEST | sig=%s",
        ("presente" if query_params.get("sig") else "ausente"),
    )

    logger.debug(
        "MOBILE REQUEST | sig3=%s",
        ("presente" if query_params.get("__NS_sig3") else "ausente"),
    )


def _registrar_response(
    response: httpx.Response,
    data: dict[str, Any] | None,
) -> None:
    logger.debug(
        "MOBILE RESPONSE | status=%d",
        response.status_code,
    )

    logger.debug(
        "MOBILE RESPONSE | content_type=%s",
        response.headers.get("content-type"),
    )

    if data is None:
        return

    logger.debug(
        "MOBILE RESPONSE | keys=%s",
        sorted(data.keys()),
    )

    logger.debug(
        "MOBILE RESPONSE | result=%r",
        data.get("result"),
    )

    logger.debug(
        "MOBILE RESPONSE | error_msg=%r",
        data.get("error_msg"),
    )

    comments = get_root_comments(data)

    logger.debug(
        "MOBILE RESPONSE | rootComments=%d",
        len(comments),
    )

    cursor = get_pcursor(data)

    logger.debug(
        "MOBILE RESPONSE | pcursor=%s",
        ("preenchido" if cursor else "ausente"),
    )


def _normalizar_params(
    query_params: dict[str, str],
) -> dict[str, str]:
    """
    Converte todas as chaves e valores
    para string.
    """
    return {str(chave): str(valor) for chave, valor in query_params.items()}


def _validar_identificadores(
    photo_id: str,
    user_id: str,
    max_comments: int,
) -> None:
    if not photo_id:
        raise KwaiCommentsError("photo_id não pode ser vazio.")

    if not photo_id.isdigit():
        raise KwaiCommentsError("photo_id deve ser numérico.")

    if not user_id:
        raise KwaiCommentsError("user_id não pode ser vazio.")

    if max_comments <= 0:
        raise KwaiCommentsError("max_comments deve ser maior que zero.")


def _remover_assinaturas_antigas(
    query_params: dict[str, str],
) -> dict[str, str]:
    """
    Remove assinaturas previamente existentes.

    Isso é importante porque cada página deve
    ser assinada novamente depois que pcursor
    e demais parâmetros estiverem definidos.
    """
    params = dict(query_params)

    for chave in (
        "sig",
        "sig2",
        "__NS_sig3",
        "__NS_sig4",
    ):
        params.pop(
            chave,
            None,
        )

    return params


def _assinar_request(
    *,
    signer: MobileRequestSigner,
    query_params: dict[str, str],
    body: dict[str, str],
) -> dict[str, str]:
    """
    Assina exatamente a request que será enviada.

    IMPORTANTE:

    Esta função deve ser chamada somente depois
    de:

    - pcursor estar definido;
    - body estar completo;
    - session params terem sido adicionados;
    - duplicidades query/body terem sido resolvidas.

    Assim uma nova página sempre recebe novas
    assinaturas.
    """

    params_sem_assinatura = _remover_assinaturas_antigas(query_params)

    try:
        sig, sig3 = signer.sign(
            query_params=dict(params_sem_assinatura),
            body=dict(body),
        )

    except Exception as exc:
        raise KwaiCommentsError(
            "Falha ao obter as assinaturas da requisição mobile."
        ) from exc

    sig = str(sig).strip()

    sig3 = str(sig3).strip()

    if not sig:
        raise KwaiCommentsError("O signer retornou sig vazia.")

    if not sig3:
        raise KwaiCommentsError("O signer retornou __NS_sig3 vazia.")

    params_assinados = dict(params_sem_assinatura)

    params_assinados["sig"] = sig

    params_assinados["__NS_sig3"] = sig3

    return params_assinados


def _request_page(
    *,
    base_url: str,
    photo_id: str,
    user_id: str,
    llsid: str,
    pcursor: str,
    count: int,
    query_params: dict[str, str],
    signer: MobileRequestSigner,
    debug: bool,
    timeout: float,
) -> dict[str, Any]:
    """
    Faz uma única request de página.

    Toda chamada dessa função monta e assina
    uma request nova.
    """

    url = f"{base_url}{MOBILE_COMMENTS_ENDPOINT}"

    # 1. Monta o body já com o pcursor
    # atual da paginação.
    body = build_root_payload(
        photo_id=photo_id,
        user_id=user_id,
        llsid=llsid,
        pcursor=pcursor,
        count=count,
    )

    # 2. Cria uma cópia dos globais.
    #
    # Nunca alteramos o dicionário original.
    request_query_params = dict(query_params)

    # 3. No fluxo observado esses parâmetros
    # pertencem ao body.
    request_query_params.pop(
        "os",
        None,
    )

    request_query_params.pop(
        "client_key",
        None,
    )

    # 4. Esses valores são montados novamente
    # em cada request.
    session_params = montar_mobile_session_params()

    body.update(session_params)

    # 5. Se uma chave existir no body,
    # ela não fica duplicada na query.
    for chave in body:
        request_query_params.pop(
            chave,
            None,
        )

    # ==================================================
    # FRONTEIRA DA ASSINATURA
    # ==================================================
    #
    # Neste momento:
    #
    # query está pronta
    # body está pronto
    # pcursor está pronto
    # session está pronta
    #
    # Portanto assinamos AGORA.
    #
    # A próxima página volta a executar tudo isso,
    # produzindo outro sig + sig3.
    # ==================================================

    request_query_params = _assinar_request(
        signer=signer,
        query_params=(request_query_params),
        body=body,
    )

    headers = _montar_mobile_headers()

    if debug:
        _registrar_request(
            url,
            request_query_params,
            body,
        )

    response = httpx.post(
        url,
        params=request_query_params,
        data=body,
        headers=headers,
        timeout=timeout,
        follow_redirects=True,
    )

    response.raise_for_status()

    try:
        data = response.json()

    except ValueError as exc:
        raise KwaiCommentsError(
            "A API mobile retornou uma resposta que não é JSON."
        ) from exc

    if not isinstance(
        data,
        dict,
    ):
        raise KwaiCommentsError("A resposta da API mobile não é um objeto JSON.")

    if debug:
        _registrar_response(
            response,
            data,
        )

    result = data.get("result")

    if result not in (
        1,
        "1",
    ):
        error_msg = data.get("error_msg")

        mensagem = str(error_msg) if error_msg is not None else ""

        assinatura_invalida = result in (
            50,
            "50",
        ) and (
            "assinatura" in mensagem.lower()
            or "signature" in mensagem.lower()
            or "sig" in mensagem.lower()
        )

        if assinatura_invalida:
            raise KwaiCommentsError(
                "A API mobile recusou "
                "a validação da requisição. "
                f"result={result!r} "
                f"error_msg={error_msg!r}"
            )

        raise KwaiCommentsError(
            f"A API mobile retornou erro. result={result!r} error_msg={error_msg!r}"
        )

    return data


def get_mobile_comments(
    photo_id: str,
    user_id: str,
    query_params: dict[str, str],
    max_comments: int,
    *,
    signer: MobileRequestSigner,
    llsid: str = "",
    debug: bool = False,
    timeout: float = DEFAULT_TIMEOUT,
) -> list[dict[str, Any]]:
    """
    Coleta até max_comments comentários
    através do endpoint mobile.

    Fluxo de cada página:

        monta request
            ↓
        adiciona pcursor
            ↓
        adiciona session params
            ↓
        resolve query/body
            ↓
        gera nova sig
            ↓
        gera nova sig3
            ↓
        envia request
            ↓
        recebe novo pcursor
            ↓
        próxima página

    max_comments representa o limite total,
    e não o tamanho de uma única página.
    """

    photo_id = str(photo_id).strip()

    user_id = str(user_id).strip()

    llsid = str(llsid).strip()

    _validar_identificadores(
        photo_id,
        user_id,
        max_comments,
    )

    params = _normalizar_params(query_params)

    comentarios: list[dict[str, Any]] = []

    ids_encontrados: set[str] = set()

    # Primeira página:
    # pcursor não será enviado.
    pcursor = ""

    cursores_encontrados: set[str] = set()

    numero_pagina = 1

    while len(comentarios) < max_comments:
        restante = max_comments - len(comentarios)

        count = min(
            ROOT_PAGE_SIZE,
            restante,
        )

        if debug:
            logger.debug(
                ("MOBILE PAGINATION | page=%d collected=%d remaining=%d pcursor=%s"),
                numero_pagina,
                len(comentarios),
                restante,
                ("preenchido" if pcursor else "vazio"),
            )

        ultimo_erro: Exception | None = None

        data: (
            dict[
                str,
                Any,
            ]
            | None
        ) = None

        for base_url in MOBILE_BASE_URLS:
            try:
                data = _request_page(
                    base_url=base_url,
                    photo_id=photo_id,
                    user_id=user_id,
                    llsid=llsid,
                    pcursor=pcursor,
                    count=count,
                    query_params=params,
                    signer=signer,
                    debug=debug,
                    timeout=timeout,
                )

                ultimo_erro = None

                break

            except (
                httpx.HTTPStatusError,
                httpx.RequestError,
                KwaiCommentsError,
            ) as exc:
                ultimo_erro = exc

        if data is None:
            if ultimo_erro is not None:
                raise KwaiCommentsError(
                    f"Não foi possível consultar a API mobile do Kwai: {ultimo_erro}"
                ) from ultimo_erro

            raise KwaiCommentsError("Não foi possível consultar a API mobile do Kwai.")

        pagina = get_root_comments(data)

        novos = 0

        for comentario in pagina:
            comment_id = get_comment_id(comentario)

            identificador = comment_id if comment_id is not None else repr(comentario)

            if identificador in ids_encontrados:
                continue

            ids_encontrados.add(identificador)

            comentarios.append(comentario)

            novos += 1

            if len(comentarios) >= max_comments:
                return comentarios[:max_comments]

        proximo_cursor = get_pcursor(data)

        if debug:
            logger.debug(
                ("MOBILE PAGINATION | page=%d received=%d new=%d next_cursor=%s"),
                numero_pagina,
                len(pagina),
                novos,
                ("preenchido" if proximo_cursor else "ausente"),
            )

        # Servidor informou que não existem
        # mais páginas.
        if is_end_cursor(proximo_cursor):
            break

        if proximo_cursor is None:
            break

        # Evita cursor repetido / loop infinito.
        if proximo_cursor in cursores_encontrados:
            logger.warning("MOBILE PAGINATION | pcursor repetido. Encerrando coleta.")

            break

        # Página não trouxe nenhum comentário novo.
        if novos == 0:
            break

        cursores_encontrados.add(proximo_cursor)

        # Este valor entra no body da PRÓXIMA
        # request.
        pcursor = proximo_cursor

        numero_pagina += 1

    return comentarios[:max_comments]

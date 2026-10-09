"""Casos de uso com portas fake: orquestração provada sem HTTP e sem ``respx``.

A arquitetura promete que os casos de uso dependem das portas
(:class:`ISearchApiPort` / :class:`IProfileApiPort` / :class:`ICommentApiPort` /
:class:`IClockPort`), não dos adapters HTTP — os fakes herdam as portas e este
arquivo demonstra o *seam*: dedupe, paginação,
limite e carimbo único provados isolados do I/O, de forma rápida e
determinística.
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any

import pytest

from src.application.dtos.collection_result import CollectionResult
from src.application.dtos.commands import (
    CommentCollectionCommand,
    ProfileCollectionCommand,
    SearchCommand,
)
from src.application.dtos.pages import (
    CommentPage,
    ProfilePage,
    RootComment,
    SubComment,
    SubCommentPage,
)
from src.application.exceptions import CollectionInterruptedError
from src.application.ports.clock_port import IClockPort
from src.application.ports.comment_api_port import ICommentApiPort
from src.application.ports.profile_api_port import IProfileApiPort
from src.application.ports.search_api_port import ISearchApiPort
from src.application.use_cases.collect_comment_versions import CollectCommentVersions
from src.application.use_cases.collect_profile_bundle import CollectProfileBundle
from src.application.use_cases.collect_user_posts import CollectUserPosts
from src.application.use_cases.search_posts import SearchPosts
from src.domain.entities.comment import Comment, CommentAuthor, ExpandedComment
from src.domain.entities.post import Engagement, Post
from src.domain.exceptions.domain_exceptions import (
    InvalidInputError,
    InvalidValueError,
    KwaiCollectorError,
    RepeatedCursorError,
)
from src.domain.services.post_urls import parse_post_reference
from src.domain.value_objects.cursor import Cursor
from src.domain.value_objects.identifiers import CommentId, Handle, UserId
from src.domain.value_objects.iso_timestamp import IsoTimestamp
from src.domain.value_objects.post_reference import PostReference


class _GatewayError(KwaiCollectorError):
    """Falha de porta simulada, sem depender das exceções da infraestrutura."""


STAMP = "2026-09-18T12:00:00Z"
POST_URL = "https://www.kwai.com/@perfil/video/123"

Lote = list[tuple[str | None, str]]


class _Clock(IClockPort):
    """Relógio fixo que conta as leituras: um carimbo por execução de caso de uso."""

    def __init__(self) -> None:
        self.calls = 0

    def now(self) -> IsoTimestamp:
        self.calls += 1
        return IsoTimestamp(STAMP)


def _search(api: FakeWebApi, keywords: list[str], **kwargs: Any) -> CollectionResult[Post]:
    return SearchPosts(api, _Clock()).execute(SearchCommand.create(keywords, **kwargs))


def _user_posts(api: FakeProfileApi, user: str, **kwargs: Any) -> list[Post]:
    command = ProfileCollectionCommand.create(user, **kwargs)
    return CollectUserPosts(api, _Clock()).execute(command)


def _comments(
    api: FakeCommentApi, *, limit: int | None = None, with_replies: bool = False
) -> CollectionResult[Comment]:
    """A única versão pedida: raízes, ou raízes com respostas."""
    command = CommentCollectionCommand.create(
        POST_URL, limit=limit, with_comments=not with_replies, with_replies=with_replies
    )
    (result,) = CollectCommentVersions(api, _Clock()).execute(command)
    return result


def _post(pid: str | None, url: str, collected_at: str) -> Post:
    return Post(id=pid, url=url, engajamento=Engagement(), coletado_em=collected_at)


def _comment(cid: str, collected_at: str, *, author_id: str = "a1") -> Comment:
    return Comment(
        id=cid,
        postagem_url=POST_URL,
        autor=CommentAuthor(usuario="@autor", id=author_id),
        texto=f"texto {cid}",
        coletado_em=collected_at,
    )


def _root(comment: Comment, declared_replies: int | None = None) -> RootComment:
    return RootComment(comment=comment, declared_replies=declared_replies)


def _sub(
    cid: str,
    collected_at: str,
    *,
    reply_to_id: str | None = None,
    reply_to_usuario: str | None = None,
) -> SubComment:
    return SubComment(
        comment=_comment(cid, collected_at),
        reply_to_id=reply_to_id,
        reply_to_usuario=reply_to_usuario,
    )


def _orphan_comment(author_id: str, text: str) -> Comment:
    """Comentário sem ``id`` (só nesse caso a chave de dedupe pode colidir)."""
    return Comment(
        id=None,
        postagem_url=POST_URL,
        autor=CommentAuthor(usuario="@autor", id=author_id),
        texto=text,
        coletado_em=STAMP,
    )


class FakeWebApi(ISearchApiPort):
    """ISearchApiPort fake: devolve lotes por palavra-chave e registra as chamadas."""

    def __init__(self, batches: dict[str, Lote] | None = None) -> None:
        self._batches = batches or {}
        self.search_calls: list[tuple[str, int, str]] = []

    def search_posts(self, keyword: str, *, limit: int, collected_at: IsoTimestamp) -> list[Post]:
        self.search_calls.append((keyword, limit, collected_at.value))
        return [_post(pid, url, collected_at.value) for pid, url in self._batches.get(keyword, [])]


class FakeProfileApi(IProfileApiPort):
    """IProfileApiPort fake: resolve o handle e serve páginas na ordem pedida."""

    def __init__(self, pages: list[ProfilePage], *, user_id: str = "150001214685137") -> None:
        self._pages = pages
        self.user_id = user_id
        self.resolve_calls: list[str] = []
        self.page_calls: list[tuple[str, str, str]] = []

    def resolve_user(self, handle: Handle) -> UserId:
        self.resolve_calls.append(handle.value)
        return UserId(self.user_id)

    def fetch_profile_page(
        self,
        user_id: UserId,
        *,
        cursor: Cursor,
        collected_at: IsoTimestamp,
    ) -> ProfilePage:
        self.page_calls.append((user_id.value, cursor.value, collected_at.value))
        assert len(self.page_calls) <= len(self._pages), "caso de uso paginou além do previsto"
        return self._pages[len(self.page_calls) - 1]


class FakeCommentApi(ICommentApiPort):
    """ICommentApiPort fake: devolve raízes e respostas pré-configuradas na ordem pedida."""

    def __init__(
        self,
        pages: list[CommentPage],
        sub_pages: dict[str, list[SubCommentPage]] | None = None,
    ) -> None:
        self._pages = pages
        self._sub_pages = sub_pages or {}
        self.calls: list[dict[str, Any]] = []
        self.sub_calls: list[tuple[str, str]] = []

    def fetch_page(
        self,
        post: PostReference,
        *,
        cursor: Cursor,
        collected_at: IsoTimestamp,
    ) -> CommentPage:
        self.calls.append(
            {
                "photo_id": post.photo_id.value,
                "cursor": cursor.value,
                "post_url": post.url,
                "collected_at": collected_at.value,
            }
        )
        assert len(self.calls) <= len(self._pages), "caso de uso paginou além do previsto"
        return self._pages[len(self.calls) - 1]

    def fetch_sub_page(
        self,
        post: PostReference,
        *,
        root_comment_id: CommentId,
        cursor: Cursor,
        collected_at: IsoTimestamp,
    ) -> SubCommentPage:
        self.sub_calls.append((root_comment_id.value, cursor.value))
        pages = self._sub_pages[root_comment_id.value]
        index = sum(1 for rid, _ in self.sub_calls if rid == root_comment_id.value) - 1
        assert index < len(pages), "caso de uso paginou a sublista além do previsto"
        return pages[index]


# --- SearchPosts ------------------------------------------------------------


def test_search_deduplica_entre_palavras_chave_pela_chave_do_dominio() -> None:
    api = FakeWebApi(
        {
            "a": [("1", "https://u/1"), ("2", "https://u/2")],
            # mesmo id repetido; e itens SEM id deduplicando pela própria URL
            "b": [
                ("1", "https://u/outro"),
                (None, "https://u/1"),
                (None, "https://u/1"),
                ("3", "https://u/3"),
            ],
        }
    )
    posts = _search(api, ["a", "b"], limit=10).items

    # "1" repetido por id; os dois (None, /u/1) viram um só pela URL.
    assert [(p.id, p.url) for p in posts] == [
        ("1", "https://u/1"),
        ("2", "https://u/2"),
        (None, "https://u/1"),
        ("3", "https://u/3"),
    ]


def test_search_faz_uma_requisicao_por_palavra_chave_com_um_carimbo_unico() -> None:
    api = FakeWebApi({"a": [("1", "u1")], "b": [("2", "u2")]})
    clock = _Clock()

    posts = SearchPosts(api, clock).execute(SearchCommand.create(["a", "b"], limit=5)).items

    assert clock.calls == 1
    assert len(api.search_calls) == 2
    assert [call[0] for call in api.search_calls] == ["a", "b"]
    assert {call[1] for call in api.search_calls} == {5}
    stamps = {call[2] for call in api.search_calls}
    assert len(stamps) == 1
    assert all(p.coletado_em == api.search_calls[0][2] for p in posts)


@pytest.mark.parametrize("limit", [0, -1])
def test_limite_nao_positivo_e_rejeitado_no_comando(limit: int) -> None:
    """O comando valida a entrada: o caso de uso nem chega a ser executado."""
    with pytest.raises(InvalidInputError, match="positivo"):
        SearchCommand.create(["a"], limit=limit)
    with pytest.raises(InvalidInputError, match="positivo"):
        ProfileCollectionCommand.create("perfil", limit=limit)
    with pytest.raises(InvalidInputError, match="positivo"):
        ProfileCollectionCommand.create("perfil", comments_limit=limit)
    with pytest.raises(InvalidInputError, match="positivo"):
        CommentCollectionCommand.create(POST_URL, limit=limit)


@pytest.mark.parametrize("keywords", [("",), ("   ",), ("\t\n",), ("válida", "")])
def test_search_rejeita_palavra_chave_em_branco_antes_de_consultar_porta(
    keywords: tuple[str, ...],
) -> None:
    api = FakeWebApi()

    with pytest.raises(InvalidInputError, match="palavra-chave"):
        SearchCommand(keywords)
    with pytest.raises(InvalidInputError, match="palavra-chave"):
        _search(api, list(keywords))

    assert api.search_calls == []


def test_search_limite_atingido_interrompe_palavras_chave_restantes() -> None:
    """Com o limite atingido na 1ª palavra-chave, a 2ª nem é requisitada."""
    api = FakeWebApi(
        {
            "a": [(str(i), f"https://u/{i}") for i in range(1, 4)],
            "b": [(str(i), f"https://u/{i}") for i in range(4, 7)],
        }
    )

    posts = _search(api, ["a", "b"], limit=3).items

    assert len(posts) == 3
    assert [p.id for p in posts] == ["1", "2", "3"]
    assert [call[0] for call in api.search_calls] == ["a"]


def test_search_falha_na_segunda_palavra_chave_preserva_a_primeira() -> None:
    class _FalhaEmB(FakeWebApi):
        def search_posts(
            self, keyword: str, *, limit: int, collected_at: IsoTimestamp
        ) -> list[Post]:
            if keyword == "b":
                raise _GatewayError("gateway fora do ar")
            return super().search_posts(keyword, limit=limit, collected_at=collected_at)

    api = _FalhaEmB({"a": [("1", "https://u/1"), ("2", "https://u/2")]})

    result = _search(api, ["a", "b"], limit=10)

    assert isinstance(result.error, CollectionInterruptedError)
    assert isinstance(result.error.__cause__, _GatewayError)
    assert _ids(result.items) == ["1", "2"]


def test_search_falha_na_primeira_palavra_chave_sem_parcial() -> None:
    class _FalhaSempre(FakeWebApi):
        def search_posts(
            self, keyword: str, *, limit: int, collected_at: IsoTimestamp
        ) -> list[Post]:
            raise _GatewayError("gateway fora do ar")

    result = _search(_FalhaSempre(), ["a"])

    assert isinstance(result.error, _GatewayError)
    assert result.items == ()


# --- CollectUserPosts -------------------------------------------------------


def _profile_page(ids: list[str], cursor: str, *, stamp: str = STAMP) -> ProfilePage:
    return ProfilePage(
        posts=[_post(pid, f"https://u/{pid}", stamp) for pid in ids],
        next_cursor=Cursor(cursor),
    )


def test_user_posts_resolve_o_handle_uma_vez_e_usa_o_id_numerico() -> None:
    api = FakeProfileApi([_profile_page(["1"], "")])

    _user_posts(api, "@perfil_teste", limit=5)

    assert api.resolve_calls == ["perfil_teste"]  # handle normalizado, sem "@"
    assert api.page_calls == [("150001214685137", "", STAMP)]


def test_user_posts_pagina_ate_o_cursor_de_fim_deduplicando() -> None:
    api = FakeProfileApi(
        [
            _profile_page(["1", "2"], "PAGE2"),
            _profile_page(["2", "3"], ""),
        ]
    )

    posts = _user_posts(api, "@perfil_teste")

    assert [p.id for p in posts] == ["1", "2", "3"]
    assert [call[1] for call in api.page_calls] == ["", "PAGE2"]


def test_user_posts_corta_no_limite_de_unicas_sem_paginar_alem() -> None:
    api = FakeProfileApi([_profile_page(["1", "2", "1", "3"], "")])

    posts = _user_posts(api, "@perfil_teste", limit=2)

    assert [p.id for p in posts] == ["1", "2"]  # "1" repetido não conta para o limite
    assert len(api.page_calls) == 1


def test_user_posts_para_quando_a_pagina_vem_vazia() -> None:
    api = FakeProfileApi([_profile_page([], "PAGE2")])

    assert _user_posts(api, "@perfil_teste") == []
    assert len(api.page_calls) == 1


def test_user_posts_usa_um_unico_carimbo_por_execucao() -> None:
    api = FakeProfileApi([_profile_page(["1"], "PAGE2"), _profile_page(["2"], "")])
    clock = _Clock()

    CollectUserPosts(api, clock).execute(ProfileCollectionCommand.create("@perfil_teste"))

    assert clock.calls == 1
    assert {call[2] for call in api.page_calls} == {STAMP}


def _ids(items: object) -> list[object]:
    """Ids dos itens coletados (parcial de uma interrupção ou de um resultado)."""
    assert isinstance(items, tuple)
    return [item.id for item in items if isinstance(item, Post | Comment)]


def test_user_posts_cursor_repetido_interrompe_com_o_parcial() -> None:
    api = FakeProfileApi(
        [
            _profile_page(["1"], "A"),
            _profile_page(["2"], "B"),
            _profile_page(["3"], "A"),
        ]
    )

    with pytest.raises(CollectionInterruptedError) as exc:
        _user_posts(api, "@perfil_teste")

    assert isinstance(exc.value.__cause__, RepeatedCursorError)
    assert _ids(exc.value.partial) == ["1", "2", "3"]
    assert len(api.page_calls) == 3


def test_user_posts_falha_na_segunda_pagina_preserva_o_que_ja_foi_coletado() -> None:
    class _FalhaNaSegundaPagina(FakeProfileApi):
        def fetch_profile_page(
            self, user_id: UserId, *, cursor: Cursor, collected_at: IsoTimestamp
        ) -> ProfilePage:
            if cursor.value:
                raise _GatewayError("gateway fora do ar")
            return super().fetch_profile_page(user_id, cursor=cursor, collected_at=collected_at)

    api = _FalhaNaSegundaPagina([_profile_page(["1", "2"], "PAGE2")])

    with pytest.raises(CollectionInterruptedError) as exc:
        _user_posts(api, "@perfil_teste")

    assert isinstance(exc.value.__cause__, _GatewayError)
    assert _ids(exc.value.partial) == ["1", "2"]


def test_user_posts_falha_na_primeira_pagina_levanta_o_erro_original() -> None:
    """Sem nada coletado não há parcial: o erro original segue sem embrulho."""

    class _FalhaNaPrimeiraPagina(FakeProfileApi):
        def fetch_profile_page(
            self, user_id: UserId, *, cursor: Cursor, collected_at: IsoTimestamp
        ) -> ProfilePage:
            raise _GatewayError("gateway fora do ar")

    with pytest.raises(_GatewayError):
        _user_posts(_FalhaNaPrimeiraPagina([]), "@perfil_teste")


def test_user_posts_erro_de_resolucao_nao_pagina() -> None:
    """Falha ao resolver o handle não chega a pedir página nenhuma."""

    class _FalhaAoResolver(FakeProfileApi):
        def resolve_user(self, handle: Handle) -> UserId:
            raise _GatewayError("gateway fora do ar")

    api = _FalhaAoResolver([_profile_page(["1"], "")])

    with pytest.raises(_GatewayError):
        _user_posts(api, "@perfil_teste")

    assert api.page_calls == []


# --- CollectCommentVersions -------------------------------------------------


def test_comments_percorre_paginas_e_deduplica_com_porta_fake() -> None:
    api = FakeCommentApi(
        [
            CommentPage(
                [_root(_comment("c1", STAMP)), _root(_comment("c2", STAMP))], Cursor("PAGE2")
            ),
            CommentPage([_root(_comment("c2", STAMP)), _root(_comment("c3", STAMP))], Cursor("")),
        ]
    )
    comments = _comments(api).items

    assert [c.id for c in comments] == ["c1", "c2", "c3"]
    assert len(api.calls) == 2
    assert [call["cursor"] for call in api.calls] == ["", "PAGE2"]
    assert {call["collected_at"] for call in api.calls} == {api.calls[0]["collected_at"]}


def test_comments_para_quando_a_primeira_pagina_traz_cursor_de_fim() -> None:
    api = FakeCommentApi(
        [CommentPage([_root(_comment("c1", STAMP)), _root(_comment("c2", STAMP))], Cursor(""))]
    )
    comments = _comments(api).items

    assert [c.id for c in comments] == ["c1", "c2"]
    assert len(api.calls) == 1


def test_comments_para_quando_a_pagina_vem_vazia_antes_do_cursor_de_fim() -> None:
    api = FakeCommentApi([CommentPage([], Cursor("PAGE2"))])
    comments = _comments(api).items

    assert comments == ()
    assert len(api.calls) == 1


def test_comments_limit_conta_itens_crus_e_corta_no_meio_da_pagina() -> None:
    page1 = CommentPage([_root(_comment(f"c{i}", STAMP)) for i in range(1, 6)], Cursor("NEXT"))
    page2 = CommentPage([_root(_comment(f"c{i}", STAMP)) for i in range(6, 11)], Cursor("NEXT2"))
    api = FakeCommentApi([page1, page2])

    comments = _comments(api, limit=7).items

    # 7º item cruo corta DENTRO da 2ª página: a 3ª página nunca é pedida.
    assert [c.id for c in comments] == [f"c{i}" for i in range(1, 8)]
    assert len(api.calls) == 2


def test_comments_sem_respostas_mantem_o_contrato_simples() -> None:
    """Sem a flag, a saída continua sendo o contrato oficial, sem chaves extras."""
    api = FakeCommentApi([CommentPage([_root(_comment("r1", STAMP), 5)], Cursor(""))])

    comments = _comments(api).items

    assert [c.id for c in comments] == ["r1"]
    assert type(comments[0]) is Comment
    assert "parent_id" not in asdict(comments[0])
    assert api.sub_calls == []


def test_comments_com_respostas_achata_raiz_e_respostas() -> None:
    api = FakeCommentApi(
        [CommentPage([_root(_comment("r1", STAMP), 2)], Cursor(""))],
        {
            "r1": [
                SubCommentPage(
                    [
                        _sub(
                            "s1",
                            STAMP,
                            reply_to_id="150001404765512",
                            reply_to_usuario="Fulano",
                        )
                    ],
                    Cursor(""),
                )
            ]
        },
    )

    comments = _comments(api, with_replies=True).items

    assert [c.id for c in comments] == ["r1", "s1"]
    raiz, resposta = comments
    assert isinstance(raiz, ExpandedComment)
    assert raiz.parent_id is None
    assert raiz.respostas_total == 2  # total declarado, não o coletado
    assert isinstance(resposta, ExpandedComment)
    assert resposta.parent_id == "r1"
    assert resposta.reply_to_id == "150001404765512"
    assert resposta.reply_to_usuario == "Fulano"
    assert resposta.respostas_total is None
    assert api.sub_calls == [("r1", "")]


def test_comments_com_respostas_nao_busca_raiz_sem_respostas() -> None:
    api = FakeCommentApi([CommentPage([_root(_comment("r1", STAMP), 0)], Cursor(""))])

    comments = _comments(api, with_replies=True).items

    assert [c.id for c in comments] == ["r1"]
    assert api.sub_calls == []
    assert comments[0].respostas_total == 0  # type: ignore[attr-defined]


def test_comments_deduplica_respostas_entre_paginas() -> None:
    api = FakeCommentApi(
        [CommentPage([_root(_comment("r1", STAMP), 3)], Cursor(""))],
        {
            "r1": [
                SubCommentPage([_sub("s1", STAMP), _sub("s2", STAMP)], Cursor("NEXT")),
                SubCommentPage([_sub("s2", STAMP), _sub("s3", STAMP)], Cursor("")),
            ]
        },
    )

    comments = _comments(api, with_replies=True).items

    assert [c.id for c in comments] == ["r1", "s1", "s2", "s3"]
    assert [call[1] for call in api.sub_calls] == ["", "NEXT"]
    assert api.sub_calls[0][0] == "r1"


def test_comments_cursor_de_sublista_repetido_pula_a_raiz_e_segue(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Uma raiz com sublista em laço não derruba as demais: warning e a coleta segue."""
    api = FakeCommentApi(
        [
            CommentPage(
                [_root(_comment("r1", STAMP), 9), _root(_comment("r2", STAMP), 1)],
                Cursor(""),
            )
        ],
        {
            "r1": [
                SubCommentPage([_sub("s1", STAMP)], Cursor("SAME")),
                SubCommentPage([_sub("s2", STAMP)], Cursor("SAME")),
            ],
            "r2": [SubCommentPage([_sub("s3", STAMP)], Cursor(""))],
        },
    )

    with caplog.at_level(logging.WARNING, logger="src.collector"):
        comments = _comments(api, with_replies=True).items

    # as respostas já lidas da raiz em laço ficam; a raiz seguinte é coletada normalmente
    assert [c.id for c in comments] == ["r1", "s1", "s2", "r2", "s3"]
    assert api.sub_calls == [("r1", ""), ("r1", "SAME"), ("r2", "")]
    assert any("r1" in record.getMessage() for record in caplog.records)


def test_comments_cursor_de_sublista_ciclo_mantem_as_respostas_lidas() -> None:
    api = FakeCommentApi(
        [CommentPage([_root(_comment("r1", STAMP), 9)], Cursor(""))],
        {
            "r1": [
                SubCommentPage([_sub("s1", STAMP)], Cursor("A")),
                SubCommentPage([_sub("s2", STAMP)], Cursor("B")),
                SubCommentPage([_sub("s3", STAMP)], Cursor("A")),
            ]
        },
    )

    comments = _comments(api, with_replies=True).items

    assert [c.id for c in comments] == ["r1", "s1", "s2", "s3"]
    assert [call[1] for call in api.sub_calls] == ["", "A", "B"]


def test_comments_falha_em_sublista_interrompe_sem_perder_as_raizes() -> None:
    """Falha ao buscar respostas não é engolida: interrompe, mas devolve o coletado."""

    class _FalhaNaSublista(FakeCommentApi):
        def fetch_sub_page(self, *args: Any, **kwargs: Any) -> SubCommentPage:
            raise _GatewayError("gateway fora do ar")

    api = _FalhaNaSublista(
        [
            CommentPage(
                [_root(_comment("r1", STAMP), 3), _root(_comment("r2", STAMP), 1)],
                Cursor(""),
            )
        ]
    )

    result = _comments(api, with_replies=True)
    assert isinstance(result.error, CollectionInterruptedError)

    assert isinstance(result.error.__cause__, _GatewayError)
    # r2 nunca teve as respostas buscadas, mas a raiz já coletada não se perde
    assert _ids(result.items) == ["r1", "r2"]
    assert all(isinstance(item, ExpandedComment) for item in result.items)


def test_comments_falha_no_meio_da_sublista_preserva_as_respostas_ja_lidas(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class _FalhaNaSegundaPaginaDaSublista(FakeCommentApi):
        def fetch_sub_page(
            self,
            post: PostReference,
            *,
            root_comment_id: CommentId,
            cursor: Cursor,
            collected_at: IsoTimestamp,
        ) -> SubCommentPage:
            if cursor.value:
                raise _GatewayError("gateway fora do ar")
            return super().fetch_sub_page(
                post,
                root_comment_id=root_comment_id,
                cursor=cursor,
                collected_at=collected_at,
            )

    api = _FalhaNaSegundaPaginaDaSublista(
        [
            CommentPage(
                [_root(_comment("r1", STAMP), 5), _root(_comment("r2", STAMP), 1)],
                Cursor(""),
            )
        ],
        {"r1": [SubCommentPage([_sub("s1", STAMP)], Cursor("NEXT"))]},
    )

    result = _comments(api, with_replies=True)
    assert isinstance(result.error, CollectionInterruptedError)

    assert _ids(result.items) == ["r1", "s1", "r2"]
    assert "declaradas=5, coletadas=1" in caplog.text


@pytest.mark.parametrize("declared", [1, 3])
def test_reply_count_difference_warns_without_losing_other_roots(
    declared: int,
    caplog: pytest.LogCaptureFixture,
) -> None:
    api = FakeCommentApi(
        [
            CommentPage(
                [_root(_comment("r1", STAMP), declared), _root(_comment("r2", STAMP), 1)],
                Cursor(""),
            )
        ],
        {
            "r1": [
                SubCommentPage([_sub("s1", STAMP)], Cursor("NEXT")),
                SubCommentPage([_sub("s1", STAMP), _sub("s2", STAMP)], Cursor("")),
            ],
            "r2": [SubCommentPage([_sub("s3", STAMP)], Cursor(""))],
        },
    )
    comments = _comments(api, with_replies=True).items
    assert [comment.id for comment in comments] == ["r1", "s1", "s2", "r2", "s3"]
    assert f"declaradas={declared}, coletadas=2" in caplog.text
    assert "causa não determinada" in caplog.text


@pytest.mark.parametrize("declared", [None, 0, 1])
def test_unknown_or_matching_reply_count_does_not_warn(
    declared: int | None,
    caplog: pytest.LogCaptureFixture,
) -> None:
    api = FakeCommentApi(
        [CommentPage([_root(_comment("r1", STAMP), declared)], Cursor(""))],
        {"r1": [SubCommentPage([_sub("s1", STAMP)], Cursor(""))]},
    )
    _comments(api, with_replies=True)
    assert "declaradas=" not in caplog.text


def test_unqueryable_root_warns_about_uncollected_declared_replies(
    caplog: pytest.LogCaptureFixture,
) -> None:
    api = FakeCommentApi([CommentPage([_root(_orphan_comment("a1", "sem id"), 5)], Cursor(""))])
    _comments(api, with_replies=True)
    assert "declaradas=5, coletadas=0" in caplog.text
    assert api.sub_calls == []


def test_comments_cursor_de_raizes_repetido_interrompe_com_o_parcial() -> None:
    api = FakeCommentApi(
        [
            CommentPage([_root(_comment("c1", STAMP))], Cursor("A")),
            CommentPage([_root(_comment("c2", STAMP))], Cursor("B")),
            CommentPage([_root(_comment("c3", STAMP))], Cursor("A")),
        ]
    )

    result = _comments(api)
    assert isinstance(result.error, CollectionInterruptedError)

    assert isinstance(result.error.__cause__, RepeatedCursorError)
    assert _ids(result.items) == ["c1", "c2", "c3"]
    assert len(api.calls) == 3


def test_comments_falha_na_segunda_pagina_de_raizes_preserva_as_primeiras() -> None:
    class _FalhaNaSegundaPagina(FakeCommentApi):
        def fetch_page(
            self,
            post: PostReference,
            *,
            cursor: Cursor,
            collected_at: IsoTimestamp,
        ) -> CommentPage:
            if cursor.value:
                raise _GatewayError("gateway fora do ar")
            return super().fetch_page(post, cursor=cursor, collected_at=collected_at)

    api = _FalhaNaSegundaPagina(
        [CommentPage([_root(_comment("c1", STAMP)), _root(_comment("c2", STAMP))], Cursor("PAGE2"))]
    )

    result = _comments(api)
    assert isinstance(result.error, CollectionInterruptedError)

    assert isinstance(result.error.__cause__, _GatewayError)
    assert _ids(result.items) == ["c1", "c2"]


def test_comments_falha_na_primeira_pagina_levanta_o_erro_original() -> None:
    class _FalhaNaPrimeiraPagina(FakeCommentApi):
        def fetch_page(self, *args: Any, **kwargs: Any) -> CommentPage:
            raise _GatewayError("gateway fora do ar")

    result = _comments(_FalhaNaPrimeiraPagina([]))

    assert isinstance(result.error, _GatewayError)
    assert result.items == ()


def test_comments_raiz_sem_id_nao_dispara_sublista() -> None:
    api = FakeCommentApi([CommentPage([_root(_orphan_comment("a1", "sem id"), 5)], Cursor(""))])

    comments = _comments(api, with_replies=True).items

    assert api.sub_calls == []
    assert comments[0].respostas_total == 5  # type: ignore[attr-defined]


def test_comments_nao_colide_chave_de_dedup_entre_respostas_sem_id() -> None:
    """Autor/texto ambíguos (sem id) não podem fundir respostas distintas."""
    api = FakeCommentApi(
        [CommentPage([_root(_comment("r1", STAMP), 2)], Cursor(""))],
        {
            "r1": [
                SubCommentPage(
                    [
                        SubComment(_orphan_comment("a:b", "c"), None, None),
                        SubComment(_orphan_comment("a", "b:c"), None, None),
                    ],
                    Cursor(""),
                )
            ]
        },
    )

    comments = _comments(api, with_replies=True).items

    assert [c.texto for c in comments] == ["texto r1", "c", "b:c"]


def test_resultado_de_comentarios_exige_post_sem_falha() -> None:
    with pytest.raises(ValueError, match="exige post"):
        CollectionResult("comments", ())
    post = parse_post_reference(POST_URL)
    assert CollectionResult("comments-replies", (), post=post).stage == "replies"
    # sem postagem identificável, só um resultado de falha é aceito
    failure: CollectionResult[Comment] = CollectionResult(
        "comments", (), error=InvalidInputError("url")
    )
    assert failure.post is None


def test_bundle_isola_postagem_sem_id_como_falha_de_comentarios() -> None:
    """Uma postagem da API sem id falha só na sua unidade; as demais seguem."""
    profile = FakeProfileApi(
        [
            ProfilePage(
                [_post(None, "https://u/sem-id", STAMP), _post("2", POST_URL, STAMP)],
                Cursor(""),
            )
        ]
    )
    comments = FakeCommentApi([CommentPage([_root(_comment("c1", STAMP))], Cursor(""))])
    command = ProfileCollectionCommand.create("perfil", with_comments=True)
    results = list(CollectProfileBundle(profile, comments, _Clock()).execute(command))

    assert [(r.kind, r.post is not None, r.error is not None) for r in results] == [
        ("posts", False, False),
        ("comments", False, True),
        ("comments", True, False),
    ]
    assert isinstance(results[1].error, InvalidValueError)
    assert _ids(results[2].items) == ["c1"]

"""Casos de uso com portas fake: orquestração provada sem HTTP e sem ``respx``.

A arquitetura promete que os casos de uso dependem das portas
(:class:`SearchApiPort` / :class:`ProfileApiPort` / :class:`CommentApiPort`),
não dos adapters HTTP — este arquivo demonstra o *seam*: dedupe, paginação,
limite e carimbo único provados isolados do I/O, de forma rápida e
determinística.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest
from pydantic import BaseModel

from src.application.collect_comments import (
    COMMENTS_PAGE_SIZE,
    SUBLIST_PAGE_SIZE,
    CollectComments,
)
from src.application.collect_user_posts import USER_POSTS_PAGE_SIZE, CollectUserPosts
from src.application.exceptions import CollectionInterruptedError, RepeatedCursorError
from src.application.models import (
    Comment,
    CommentAuthor,
    Engagement,
    ExpandedComment,
    Post,
)
from src.application.ports import (
    CommentPage,
    ProfilePage,
    RootComment,
    SubComment,
    SubCommentPage,
)
from src.application.search_posts import SEARCH_MAX_COUNT, SearchPosts
from src.domain.value_objects.cursor import Cursor
from src.domain.value_objects.identifiers import CommentId, Handle, PhotoId, UserId
from src.domain.value_objects.iso_timestamp import IsoTimestamp
from src.infrastructure.exceptions import KwaiTransportError

STAMP = "2026-09-18T12:00:00Z"
POST_URL = "https://www.kwai.com/@perfil/video/123"

Lote = list[tuple[str | None, str]]


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


def _root(comment: Comment, respostas_declaradas: int | None = None) -> RootComment:
    return RootComment(comentario=comment, respostas_declaradas=respostas_declaradas)


def _sub(
    cid: str,
    collected_at: str,
    *,
    reply_to_id: str | None = None,
    reply_to_usuario: str | None = None,
) -> SubComment:
    return SubComment(
        comentario=_comment(cid, collected_at),
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


class FakeWebApi:
    """SearchApiPort fake: devolve lotes por palavra-chave e registra as chamadas."""

    def __init__(self, batches: dict[str, Lote] | None = None) -> None:
        self._batches = batches or {}
        self.search_calls: list[tuple[str, int, str]] = []

    def search_posts(self, keyword: str, count: int, *, collected_at: IsoTimestamp) -> list[Post]:
        self.search_calls.append((keyword, count, collected_at.value))
        return [_post(pid, url, collected_at.value) for pid, url in self._batches.get(keyword, [])]


class FakeProfileApi:
    """ProfileApiPort fake: resolve o handle e serve páginas na ordem pedida."""

    def __init__(self, pages: list[ProfilePage], *, user_id: str = "150001214685137") -> None:
        self._pages = pages
        self.user_id = user_id
        self.resolve_calls: list[str] = []
        self.page_calls: list[tuple[str, str, int, str]] = []

    def resolve_user(self, handle: Handle) -> UserId:
        self.resolve_calls.append(handle.value)
        return UserId(self.user_id)

    def fetch_profile_page(
        self,
        user_id: UserId,
        *,
        cursor: Cursor,
        count: int,
        collected_at: IsoTimestamp,
    ) -> ProfilePage:
        self.page_calls.append((user_id.value, cursor.value, count, collected_at.value))
        assert len(self.page_calls) <= len(self._pages), "caso de uso paginou além do previsto"
        return self._pages[len(self.page_calls) - 1]


class FakeCommentApi:
    """CommentApiPort fake: devolve raízes e respostas pré-configuradas na ordem pedida."""

    def __init__(
        self,
        pages: list[CommentPage],
        sub_pages: dict[str, list[SubCommentPage]] | None = None,
    ) -> None:
        self._pages = pages
        self._sub_pages = sub_pages or {}
        self.calls: list[dict[str, Any]] = []
        self.sub_calls: list[tuple[str, str]] = []
        self.sub_counts: list[int] = []

    def fetch_page(
        self,
        photo_id: PhotoId,
        *,
        cursor: Cursor,
        count: int,
        postagem_url: str,
        collected_at: IsoTimestamp,
    ) -> CommentPage:
        self.calls.append(
            {
                "photo_id": photo_id.value,
                "cursor": cursor.value,
                "count": count,
                "postagem_url": postagem_url,
                "collected_at": collected_at.value,
            }
        )
        assert len(self.calls) <= len(self._pages), "caso de uso paginou além do previsto"
        return self._pages[len(self.calls) - 1]

    def fetch_sub_page(
        self,
        photo_id: PhotoId,
        *,
        root_comment_id: CommentId,
        cursor: Cursor,
        count: int,
        postagem_url: str,
        collected_at: IsoTimestamp,
    ) -> SubCommentPage:
        self.sub_calls.append((root_comment_id.value, cursor.value))
        self.sub_counts.append(count)
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
    posts = SearchPosts(api).execute(["a", "b"], limit=10)

    # "1" repetido por id; os dois (None, /u/1) viram um só pela URL.
    assert [(p.id, p.url) for p in posts] == [
        ("1", "https://u/1"),
        ("2", "https://u/2"),
        (None, "https://u/1"),
        ("3", "https://u/3"),
    ]


def test_search_faz_uma_requisicao_por_palavra_chave_com_um_carimbo_unico() -> None:
    api = FakeWebApi({"a": [("1", "u1")], "b": [("2", "u2")]})

    posts = SearchPosts(api).execute(["a", "b"], limit=5)

    assert len(api.search_calls) == 2
    assert [call[0] for call in api.search_calls] == ["a", "b"]
    assert {call[1] for call in api.search_calls} == {5}
    stamps = {call[2] for call in api.search_calls}
    assert len(stamps) == 1
    assert all(p.coletado_em == api.search_calls[0][2] for p in posts)


def test_search_limita_count_ao_maximo_e_ao_minimo_do_endpoint() -> None:
    alto = FakeWebApi()
    SearchPosts(alto).execute(["a"], limit=10_000)
    baixo = FakeWebApi()
    SearchPosts(baixo).execute(["b"], limit=0)

    assert alto.search_calls[0][1] == SEARCH_MAX_COUNT
    assert baixo.search_calls[0][1] == 1


def test_search_limite_atingido_interrompe_palavras_chave_restantes() -> None:
    """Com o limite atingido na 1ª palavra-chave, a 2ª nem é requisitada."""
    api = FakeWebApi(
        {
            "a": [(str(i), f"https://u/{i}") for i in range(1, 4)],
            "b": [(str(i), f"https://u/{i}") for i in range(4, 7)],
        }
    )

    posts = SearchPosts(api).execute(["a", "b"], limit=3)

    assert len(posts) == 3
    assert [p.id for p in posts] == ["1", "2", "3"]
    assert [call[0] for call in api.search_calls] == ["a"]


def test_search_falha_na_segunda_palavra_chave_preserva_a_primeira() -> None:
    class _FalhaEmB(FakeWebApi):
        def search_posts(
            self, keyword: str, count: int, *, collected_at: IsoTimestamp
        ) -> list[Post]:
            if keyword == "b":
                raise KwaiTransportError("gateway fora do ar")
            return super().search_posts(keyword, count, collected_at=collected_at)

    api = _FalhaEmB({"a": [("1", "https://u/1"), ("2", "https://u/2")]})

    with pytest.raises(CollectionInterruptedError) as exc:
        SearchPosts(api).execute(["a", "b"], limit=10)

    assert isinstance(exc.value.__cause__, KwaiTransportError)
    assert [item.model_dump()["id"] for item in exc.value.partial] == ["1", "2"]


# --- CollectUserPosts -------------------------------------------------------


def _profile_page(ids: list[str], cursor: str, *, stamp: str = STAMP) -> ProfilePage:
    return ProfilePage(
        posts=[_post(pid, f"https://u/{pid}", stamp) for pid in ids],
        next_cursor=Cursor(cursor),
    )


def test_user_posts_resolve_o_handle_uma_vez_e_usa_o_id_numerico() -> None:
    api = FakeProfileApi([_profile_page(["1"], "no_more")])

    CollectUserPosts(api).execute("@perfil_teste", limit=5)

    assert api.resolve_calls == ["perfil_teste"]  # handle normalizado, sem "@"
    assert api.page_calls == [("150001214685137", "", USER_POSTS_PAGE_SIZE, api.page_calls[0][3])]


def test_user_posts_pagina_ate_o_cursor_de_fim_deduplicando() -> None:
    api = FakeProfileApi(
        [
            _profile_page(["1", "2"], "PAGE2"),
            _profile_page(["2", "3"], "no_more"),
        ]
    )

    posts = CollectUserPosts(api).execute("@perfil_teste")

    assert [p.id for p in posts] == ["1", "2", "3"]
    assert [call[1] for call in api.page_calls] == ["", "PAGE2"]


def test_user_posts_corta_no_limite_de_unicas_sem_paginar_alem() -> None:
    api = FakeProfileApi([_profile_page(["1", "2", "1", "3"], "no_more")])

    posts = CollectUserPosts(api).execute("@perfil_teste", limit=2)

    assert [p.id for p in posts] == ["1", "2"]  # "1" repetido não conta para o limite
    assert len(api.page_calls) == 1


def test_user_posts_para_quando_a_pagina_vem_vazia() -> None:
    api = FakeProfileApi([_profile_page([], "PAGE2")])

    assert CollectUserPosts(api).execute("@perfil_teste") == []
    assert len(api.page_calls) == 1


def test_user_posts_usa_um_unico_carimbo_por_execucao() -> None:
    api = FakeProfileApi([_profile_page(["1"], "PAGE2"), _profile_page(["2"], "no_more")])

    CollectUserPosts(api).execute("@perfil_teste")

    assert {call[3] for call in api.page_calls} == {api.page_calls[0][3]}


def _ids(items: object) -> list[object]:
    """Ids do parcial de uma interrupção (``partial`` é uma sequência de modelos)."""
    assert isinstance(items, tuple)
    return [item.model_dump()["id"] for item in items if isinstance(item, BaseModel)]


def test_user_posts_cursor_repetido_interrompe_com_o_parcial() -> None:
    api = FakeProfileApi(
        [
            _profile_page(["1"], "A"),
            _profile_page(["2"], "B"),
            _profile_page(["3"], "A"),
        ]
    )

    with pytest.raises(CollectionInterruptedError) as exc:
        CollectUserPosts(api).execute("@perfil_teste")

    assert isinstance(exc.value.__cause__, RepeatedCursorError)
    assert _ids(exc.value.partial) == ["1", "2", "3"]
    assert len(api.page_calls) == 3


def test_user_posts_falha_na_segunda_pagina_preserva_o_que_ja_foi_coletado() -> None:
    class _FalhaNaSegundaPagina(FakeProfileApi):
        def fetch_profile_page(
            self, user_id: UserId, *, cursor: Cursor, count: int, collected_at: IsoTimestamp
        ) -> ProfilePage:
            if cursor.value:
                raise KwaiTransportError("gateway fora do ar")
            return super().fetch_profile_page(
                user_id, cursor=cursor, count=count, collected_at=collected_at
            )

    api = _FalhaNaSegundaPagina([_profile_page(["1", "2"], "PAGE2")])

    with pytest.raises(CollectionInterruptedError) as exc:
        CollectUserPosts(api).execute("@perfil_teste")

    assert isinstance(exc.value.__cause__, KwaiTransportError)
    assert _ids(exc.value.partial) == ["1", "2"]


def test_user_posts_falha_na_primeira_pagina_levanta_o_erro_original() -> None:
    """Sem nada coletado não há parcial: o erro original segue sem embrulho."""

    class _FalhaNaPrimeiraPagina(FakeProfileApi):
        def fetch_profile_page(
            self, user_id: UserId, *, cursor: Cursor, count: int, collected_at: IsoTimestamp
        ) -> ProfilePage:
            raise KwaiTransportError("gateway fora do ar")

    with pytest.raises(KwaiTransportError):
        CollectUserPosts(_FalhaNaPrimeiraPagina([])).execute("@perfil_teste")


def test_user_posts_erro_de_resolucao_nao_pagina() -> None:
    """Falha ao resolver o handle não chega a pedir página nenhuma."""

    class _FalhaAoResolver(FakeProfileApi):
        def resolve_user(self, handle: Handle) -> UserId:
            raise KwaiTransportError("gateway fora do ar")

    api = _FalhaAoResolver([_profile_page(["1"], "no_more")])

    with pytest.raises(KwaiTransportError):
        CollectUserPosts(api).execute("@perfil_teste")

    assert api.page_calls == []


# --- CollectComments --------------------------------------------------------


def test_comments_percorre_paginas_e_deduplica_com_porta_fake() -> None:
    api = FakeCommentApi(
        [
            CommentPage(
                [_root(_comment("c1", STAMP)), _root(_comment("c2", STAMP))], Cursor("PAGE2")
            ),
            CommentPage(
                [_root(_comment("c2", STAMP)), _root(_comment("c3", STAMP))], Cursor("no_more")
            ),
        ]
    )
    comments = CollectComments(api).execute(POST_URL)

    assert [c.id for c in comments] == ["c1", "c2", "c3"]
    assert len(api.calls) == 2
    assert [call["cursor"] for call in api.calls] == ["", "PAGE2"]
    assert {call["count"] for call in api.calls} == {COMMENTS_PAGE_SIZE}
    assert {call["collected_at"] for call in api.calls} == {api.calls[0]["collected_at"]}


def test_comments_para_quando_a_primeira_pagina_traz_cursor_de_fim() -> None:
    api = FakeCommentApi(
        [CommentPage([_root(_comment("c1", STAMP)), _root(_comment("c2", STAMP))], Cursor("0"))]
    )
    comments = CollectComments(api).execute(POST_URL)

    assert [c.id for c in comments] == ["c1", "c2"]
    assert len(api.calls) == 1


def test_comments_para_quando_a_pagina_vem_vazia_antes_do_cursor_de_fim() -> None:
    api = FakeCommentApi([CommentPage([], Cursor("PAGE2"))])
    comments = CollectComments(api).execute(POST_URL)

    assert comments == []
    assert len(api.calls) == 1


def test_comments_limit_conta_itens_crus_e_corta_no_meio_da_pagina() -> None:
    page1 = CommentPage([_root(_comment(f"c{i}", STAMP)) for i in range(1, 6)], Cursor("NEXT"))
    page2 = CommentPage([_root(_comment(f"c{i}", STAMP)) for i in range(6, 11)], Cursor("NEXT2"))
    api = FakeCommentApi([page1, page2])

    comments = CollectComments(api).execute(POST_URL, limit=7)

    # 7º item cruo corta DENTRO da 2ª página: a 3ª página nunca é pedida.
    assert [c.id for c in comments] == [f"c{i}" for i in range(1, 8)]
    assert len(api.calls) == 2


def test_comments_sem_respostas_mantem_o_contrato_simples() -> None:
    """Sem a flag, a saída continua sendo o contrato oficial, sem chaves extras."""
    api = FakeCommentApi([CommentPage([_root(_comment("r1", STAMP), 5)], Cursor("no_more"))])

    comments = CollectComments(api).execute(POST_URL)

    assert [c.id for c in comments] == ["r1"]
    assert type(comments[0]) is Comment
    assert "parent_id" not in comments[0].model_dump()
    assert api.sub_calls == []


def test_comments_com_respostas_achata_raiz_e_respostas() -> None:
    api = FakeCommentApi(
        [CommentPage([_root(_comment("r1", STAMP), 2)], Cursor("no_more"))],
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
                    Cursor("no_more"),
                )
            ]
        },
    )

    comments = CollectComments(api).execute(POST_URL, with_replies=True)

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
    api = FakeCommentApi([CommentPage([_root(_comment("r1", STAMP), 0)], Cursor("no_more"))])

    comments = CollectComments(api).execute(POST_URL, with_replies=True)

    assert [c.id for c in comments] == ["r1"]
    assert api.sub_calls == []
    assert comments[0].respostas_total == 0  # type: ignore[attr-defined]


def test_comments_deduplica_respostas_entre_paginas() -> None:
    api = FakeCommentApi(
        [CommentPage([_root(_comment("r1", STAMP), 3)], Cursor("no_more"))],
        {
            "r1": [
                SubCommentPage([_sub("s1", STAMP), _sub("s2", STAMP)], Cursor("NEXT")),
                SubCommentPage([_sub("s2", STAMP), _sub("s3", STAMP)], Cursor("no_more")),
            ]
        },
    )

    comments = CollectComments(api).execute(POST_URL, with_replies=True)

    assert [c.id for c in comments] == ["r1", "s1", "s2", "s3"]
    assert [call[1] for call in api.sub_calls] == ["", "NEXT"]
    assert api.sub_calls[0][0] == "r1"


def test_comments_usa_a_sublist_page_size() -> None:
    api = FakeCommentApi(
        [CommentPage([_root(_comment("r1", STAMP), 1)], Cursor("no_more"))],
        {"r1": [SubCommentPage([_sub("s1", STAMP)], Cursor("no_more"))]},
    )

    CollectComments(api).execute(POST_URL, with_replies=True)

    assert api.sub_counts == [SUBLIST_PAGE_SIZE]


def test_comments_cursor_de_sublista_repetido_pula_a_raiz_e_segue(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Uma raiz com sublista em laço não derruba as demais: warning e a coleta segue."""
    api = FakeCommentApi(
        [
            CommentPage(
                [_root(_comment("r1", STAMP), 9), _root(_comment("r2", STAMP), 1)],
                Cursor("no_more"),
            )
        ],
        {
            "r1": [
                SubCommentPage([_sub("s1", STAMP)], Cursor("SAME")),
                SubCommentPage([_sub("s2", STAMP)], Cursor("SAME")),
            ],
            "r2": [SubCommentPage([_sub("s3", STAMP)], Cursor("no_more"))],
        },
    )

    with caplog.at_level(logging.WARNING, logger="src.collector"):
        comments = CollectComments(api).execute(POST_URL, with_replies=True)

    # as respostas já lidas da raiz em laço ficam; a raiz seguinte é coletada normalmente
    assert [c.id for c in comments] == ["r1", "s1", "s2", "r2", "s3"]
    assert api.sub_calls == [("r1", ""), ("r1", "SAME"), ("r2", "")]
    assert any("r1" in record.getMessage() for record in caplog.records)


def test_comments_cursor_de_sublista_ciclo_mantem_as_respostas_lidas() -> None:
    api = FakeCommentApi(
        [CommentPage([_root(_comment("r1", STAMP), 9)], Cursor("no_more"))],
        {
            "r1": [
                SubCommentPage([_sub("s1", STAMP)], Cursor("A")),
                SubCommentPage([_sub("s2", STAMP)], Cursor("B")),
                SubCommentPage([_sub("s3", STAMP)], Cursor("A")),
            ]
        },
    )

    comments = CollectComments(api).execute(POST_URL, with_replies=True)

    assert [c.id for c in comments] == ["r1", "s1", "s2", "s3"]
    assert [call[1] for call in api.sub_calls] == ["", "A", "B"]


def test_comments_falha_em_sublista_interrompe_sem_perder_as_raizes() -> None:
    """Falha ao buscar respostas não é engolida: interrompe, mas devolve o coletado."""

    class _FalhaNaSublista(FakeCommentApi):
        def fetch_sub_page(self, *args: Any, **kwargs: Any) -> SubCommentPage:
            raise KwaiTransportError("gateway fora do ar")

    api = _FalhaNaSublista(
        [
            CommentPage(
                [_root(_comment("r1", STAMP), 3), _root(_comment("r2", STAMP), 1)],
                Cursor("no_more"),
            )
        ]
    )

    with pytest.raises(CollectionInterruptedError) as exc:
        CollectComments(api).execute(POST_URL, with_replies=True)

    assert isinstance(exc.value.__cause__, KwaiTransportError)
    # r2 nunca teve as respostas buscadas, mas a raiz já coletada não se perde
    assert _ids(exc.value.partial) == ["r1", "r2"]
    assert all(isinstance(item, ExpandedComment) for item in exc.value.partial)


def test_comments_falha_no_meio_da_sublista_preserva_as_respostas_ja_lidas(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class _FalhaNaSegundaPaginaDaSublista(FakeCommentApi):
        def fetch_sub_page(
            self,
            photo_id: PhotoId,
            *,
            root_comment_id: CommentId,
            cursor: Cursor,
            count: int,
            postagem_url: str,
            collected_at: IsoTimestamp,
        ) -> SubCommentPage:
            if cursor.value:
                raise KwaiTransportError("gateway fora do ar")
            return super().fetch_sub_page(
                photo_id,
                root_comment_id=root_comment_id,
                cursor=cursor,
                count=count,
                postagem_url=postagem_url,
                collected_at=collected_at,
            )

    api = _FalhaNaSegundaPaginaDaSublista(
        [
            CommentPage(
                [_root(_comment("r1", STAMP), 5), _root(_comment("r2", STAMP), 1)],
                Cursor("no_more"),
            )
        ],
        {"r1": [SubCommentPage([_sub("s1", STAMP)], Cursor("NEXT"))]},
    )

    with pytest.raises(CollectionInterruptedError) as exc:
        CollectComments(api).execute(POST_URL, with_replies=True)

    assert _ids(exc.value.partial) == ["r1", "s1", "r2"]
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
                Cursor("no_more"),
            )
        ],
        {
            "r1": [
                SubCommentPage([_sub("s1", STAMP)], Cursor("NEXT")),
                SubCommentPage([_sub("s1", STAMP), _sub("s2", STAMP)], Cursor("no_more")),
            ],
            "r2": [SubCommentPage([_sub("s3", STAMP)], Cursor("no_more"))],
        },
    )
    comments = CollectComments(api).execute(POST_URL, with_replies=True)
    assert [comment.id for comment in comments] == ["r1", "s1", "s2", "r2", "s3"]
    assert f"declaradas={declared}, coletadas=2" in caplog.text
    assert "causa não determinada" in caplog.text


@pytest.mark.parametrize("declared", [None, 0, 1])
def test_unknown_or_matching_reply_count_does_not_warn(
    declared: int | None,
    caplog: pytest.LogCaptureFixture,
) -> None:
    api = FakeCommentApi(
        [CommentPage([_root(_comment("r1", STAMP), declared)], Cursor("no_more"))],
        {"r1": [SubCommentPage([_sub("s1", STAMP)], Cursor("no_more"))]},
    )
    CollectComments(api).execute(POST_URL, with_replies=True)
    assert "declaradas=" not in caplog.text


def test_unqueryable_root_warns_about_uncollected_declared_replies(
    caplog: pytest.LogCaptureFixture,
) -> None:
    api = FakeCommentApi(
        [CommentPage([_root(_orphan_comment("a1", "sem id"), 5)], Cursor("no_more"))]
    )
    CollectComments(api).execute(POST_URL, with_replies=True)
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

    with pytest.raises(CollectionInterruptedError) as exc:
        CollectComments(api).execute(POST_URL)

    assert isinstance(exc.value.__cause__, RepeatedCursorError)
    assert _ids(exc.value.partial) == ["c1", "c2", "c3"]
    assert len(api.calls) == 3


def test_comments_falha_na_segunda_pagina_de_raizes_preserva_as_primeiras() -> None:
    class _FalhaNaSegundaPagina(FakeCommentApi):
        def fetch_page(
            self,
            photo_id: PhotoId,
            *,
            cursor: Cursor,
            count: int,
            postagem_url: str,
            collected_at: IsoTimestamp,
        ) -> CommentPage:
            if cursor.value:
                raise KwaiTransportError("gateway fora do ar")
            return super().fetch_page(
                photo_id,
                cursor=cursor,
                count=count,
                postagem_url=postagem_url,
                collected_at=collected_at,
            )

    api = _FalhaNaSegundaPagina(
        [CommentPage([_root(_comment("c1", STAMP)), _root(_comment("c2", STAMP))], Cursor("PAGE2"))]
    )

    with pytest.raises(CollectionInterruptedError) as exc:
        CollectComments(api).execute(POST_URL)

    assert isinstance(exc.value.__cause__, KwaiTransportError)
    assert _ids(exc.value.partial) == ["c1", "c2"]


def test_comments_falha_na_primeira_pagina_levanta_o_erro_original() -> None:
    class _FalhaNaPrimeiraPagina(FakeCommentApi):
        def fetch_page(self, *args: Any, **kwargs: Any) -> CommentPage:
            raise KwaiTransportError("gateway fora do ar")

    with pytest.raises(KwaiTransportError):
        CollectComments(_FalhaNaPrimeiraPagina([])).execute(POST_URL)


def test_comments_raiz_sem_id_nao_dispara_sublista() -> None:
    api = FakeCommentApi(
        [CommentPage([_root(_orphan_comment("a1", "sem id"), 5)], Cursor("no_more"))]
    )

    comments = CollectComments(api).execute(POST_URL, with_replies=True)

    assert api.sub_calls == []
    assert comments[0].respostas_total == 5  # type: ignore[attr-defined]


def test_comments_nao_colide_chave_de_dedup_entre_respostas_sem_id() -> None:
    """Autor/texto ambíguos (sem id) não podem fundir respostas distintas."""
    api = FakeCommentApi(
        [CommentPage([_root(_comment("r1", STAMP), 2)], Cursor("no_more"))],
        {
            "r1": [
                SubCommentPage(
                    [
                        SubComment(_orphan_comment("a:b", "c"), None, None),
                        SubComment(_orphan_comment("a", "b:c"), None, None),
                    ],
                    Cursor("no_more"),
                )
            ]
        },
    )

    comments = CollectComments(api).execute(POST_URL, with_replies=True)

    assert [c.texto for c in comments] == ["texto r1", "c", "b:c"]

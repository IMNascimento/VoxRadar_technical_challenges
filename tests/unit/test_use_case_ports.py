"""Composição de coletas por portas de entrada, sem implementações concretas."""

from __future__ import annotations

from collections.abc import Iterator

from src.application.dtos.collection_result import CollectionResult
from src.application.dtos.commands import (
    CommentCollectionCommand,
    CommentVersions,
    ProfileCollectionCommand,
)
from src.application.ports.use_case_ports import ICollectCommentVersionsPort, ICollectUserPostsPort
from src.application.use_cases.collect_profile_bundle import CollectProfileBundle
from src.domain.entities.comment import Comment
from src.domain.entities.post import Engagement, Post


class _Posts(ICollectUserPostsPort):
    def __init__(self, post: Post) -> None:
        self.post = post
        self.commands: list[ProfileCollectionCommand] = []

    def execute(self, command: ProfileCollectionCommand) -> list[Post]:
        self.commands.append(command)
        return [self.post]


class _Comments(ICollectCommentVersionsPort):
    def __init__(self) -> None:
        self.commands: list[CommentCollectionCommand] = []

    def execute(self, command: CommentCollectionCommand) -> Iterator[CollectionResult[Comment]]:
        self.commands.append(command)
        yield CollectionResult("comments", (), post=command.post)


def test_bundle_compoe_portas_e_entrega_posts_antes_de_consultar_comentarios() -> None:
    post = Post(
        id="123",
        url="https://www.kwai.com/@perfil/video/123",
        engajamento=Engagement(),
        coletado_em="2026-10-09T12:00:00Z",
    )
    posts = _Posts(post)
    comments = _Comments()
    command = ProfileCollectionCommand.create(
        "perfil", comments_limit=2, comment_versions=CommentVersions.ROOTS
    )

    results = CollectProfileBundle(posts, comments).execute(command)
    assert next(results).items == (post,)
    assert posts.commands == [command]
    assert comments.commands == []

    result = next(results)
    assert result.kind == "comments"
    assert result.post is not None
    assert result.post.photo_id.value == "123"
    assert comments.commands == [CommentCollectionCommand(result.post, 2, CommentVersions.ROOTS)]
    assert list(results) == []

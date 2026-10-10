"""A1_Radar."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

PostRaw = dict[str, Any]
PostNormalizado = dict[str, Any]

SearchPostsFn = Callable[..., list[PostRaw]]
GetProfilePostsFn = Callable[..., list[PostRaw]]

NormalizePostsFn = Callable[
    [list[PostRaw]],
    list[PostNormalizado],
]

SaveJsonFn = Callable[
    [object, Path],
    None,
]

SafeNameFn = Callable[
    [str],
    str,
]

CleanUserFn = Callable[
    [str],
    str,
]


@dataclass(frozen=True, slots=True)
class SearchCommandResult:
    exit_code: int
    raw_posts: list[PostRaw]
    posts: list[PostNormalizado]
    output_path: Path | None


@dataclass(frozen=True, slots=True)
class SearchCommand:
    search_posts: SearchPostsFn
    normalize_posts: NormalizePostsFn
    safe_filename: SafeNameFn
    save_json: SaveJsonFn
    logger: logging.Logger

    def execute(
        self,
        keyword: str,
        output_dir: Path,
        delay: float,
    ) -> int:
        return self.run(
            keyword=keyword,
            output_dir=output_dir,
            delay=delay,
        ).exit_code

    def run(
        self,
        *,
        keyword: str,
        output_dir: Path,
        delay: float,
    ) -> SearchCommandResult:
        normalized_keyword = keyword.strip()

        if not normalized_keyword:
            self.logger.error("Informe uma palavra-chave válida.")
            return SearchCommandResult(
                exit_code=1,
                raw_posts=[],
                posts=[],
                output_path=None,
            )

        self.logger.info(
            "Buscando posts por: %s",
            normalized_keyword,
        )

        raw_posts = self._fetch_posts(
            normalized_keyword,
            delay,
        )

        if raw_posts is None:
            return SearchCommandResult(
                exit_code=1,
                raw_posts=[],
                posts=[],
                output_path=None,
            )

        posts = self.normalize_posts(raw_posts)

        output_path = output_dir / (
            f"busca_{self.safe_filename(normalized_keyword)}.json"
        )

        self.save_json(
            posts,
            output_path,
        )

        self.logger.info("Busca concluída.")

        self.logger.info(
            "Posts coletados: %d",
            len(posts),
        )

        self.logger.info(
            "Arquivo salvo em: %s",
            output_path,
        )

        return SearchCommandResult(
            exit_code=0,
            raw_posts=raw_posts,
            posts=posts,
            output_path=output_path,
        )

    def _fetch_posts(
        self,
        keyword: str,
        delay: float,
    ) -> list[PostRaw] | None:
        try:
            return self.search_posts(
                keyword,
                delay=delay,
            )
        except (
            httpx.RequestError,
            httpx.HTTPStatusError,
            RuntimeError,
        ) as exc:
            self.logger.error(
                "Falha ao buscar posts: %s",
                exc,
            )
            return None


@dataclass(frozen=True, slots=True)
class ProfileCommand:
    clean_user: CleanUserFn
    get_profile_posts: GetProfilePostsFn
    normalize_posts: NormalizePostsFn
    safe_filename: SafeNameFn
    save_json: SaveJsonFn
    logger: logging.Logger

    def execute(
        self,
        profile: str,
        output_dir: Path,
        delay: float,
    ) -> int:
        user = self._normalize_user(profile)

        if user is None:
            return 1

        query_user = f"@{user}"

        self.logger.info(
            "Coletando posts do perfil: %s",
            query_user,
        )

        raw_posts = self._fetch_posts(
            query_user,
            delay,
        )

        if raw_posts is None:
            return 1

        if not raw_posts:
            self.logger.error(
                "Nenhuma postagem encontrada para o perfil %s.",
                query_user,
            )
            return 1

        posts = self.normalize_posts(raw_posts)

        if not posts:
            self.logger.error(
                "Nenhuma postagem válida encontrada para o perfil %s.",
                query_user,
            )
            return 1

        output_path = output_dir / (f"{self.safe_filename(user)}_posts.json")

        self.save_json(
            posts,
            output_path,
        )

        self.logger.info("Coleta do perfil concluída.")

        self.logger.info(
            "Posts coletados: %d",
            len(posts),
        )

        self.logger.info(
            "Arquivo salvo em: %s",
            output_path,
        )

        return 0

    def _normalize_user(
        self,
        profile: str,
    ) -> str | None:
        try:
            return self.clean_user(profile)
        except ValueError as exc:
            self.logger.error(
                "%s",
                exc,
            )
            return None

    def _fetch_posts(
        self,
        user: str,
        delay: float,
    ) -> list[PostRaw] | None:
        try:
            return self.get_profile_posts(
                user_id=user,
                delay=delay,
            )
        except (
            httpx.RequestError,
            httpx.HTTPStatusError,
            RuntimeError,
        ) as exc:
            self.logger.error(
                "Falha ao coletar o perfil: %s",
                exc,
            )
            return None

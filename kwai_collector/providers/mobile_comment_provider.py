"""A1_Radar."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from kwai_collector.clients.comment_collection_progress import (
    CommentCollectionInterrupted,
    CommentCollectionProgress,
)
from kwai_collector.clients.live_comment_client import (
    LiveCommentClient,
    extract_ids_from_url,
)
from kwai_collector.clients.mobile_comment_client import (
    collect_root_pages,
)
from kwai_collector.models.comentario import Comentario
from kwai_collector.parsers.comment_parser import (
    parse_comment,
)
from kwai_collector.providers.comment_checkpoint import (
    load_comment_checkpoint,
    save_comment_checkpoint,
)
from kwai_collector.security.android_profile_mobile_request_provider import (
    AndroidProfileMobileRequestProvider,
)
from kwai_collector.security.configured_mobile_request_provider import (
    ConfiguredMobileRequestProvider,
)
from kwai_collector.security.signature_provider import (
    MobileRequestProvider,
)

logger = logging.getLogger(__name__)


class MobileCommentProvider:
    def __init__(
        self,
        arquivo_json: Path | None = None,
        auth_provider: MobileRequestProvider | None = None,
    ) -> None:
        self.arquivo_json = arquivo_json
        self.auth_provider = auth_provider
        self.live_client: LiveCommentClient | None = None
        self.max_attempts = 3
        self.backoff_base = 1.0
        self.page_delay = 1.0
        self.checkpoint_path: Path | None = None
        self.resume_collection = False

    def _load_pages(
        self,
    ) -> list[dict[str, Any]]:
        """
        Carrega uma ou várias páginas de comentários
        de um arquivo JSON.

        Formatos aceitos:

        1. Uma página:
           {
               "rootComments": [...],
               "pcursor": "no_more"
           }

        2. Várias páginas:
           [
               {
                   "rootComments": [...],
                   "pcursor": "cursor_1"
               },
               {
                   "rootComments": [...],
                   "pcursor": "no_more"
               }
           ]
        """
        if self.arquivo_json is None:
            return []

        if not self.arquivo_json.exists():
            raise FileNotFoundError(f"Arquivo não encontrado: {self.arquivo_json}")

        with self.arquivo_json.open(
            "r",
            encoding="utf-8",
        ) as arquivo:
            data = json.load(arquivo)

        if isinstance(
            data,
            dict,
        ):
            return [data]

        if isinstance(
            data,
            list,
        ):
            return [
                item
                for item in data
                if isinstance(
                    item,
                    dict,
                )
            ]

        raise TypeError("O arquivo JSON deve conter um objeto ou uma lista de objetos.")

    def _get_comments_from_file(
        self,
        postagem_url: str,
        max_comments: int | None,
    ) -> list[Comentario]:
        pages = self._load_pages()

        comentarios_brutos = collect_root_pages(
            pages,
            max_comments=max_comments,
        )

        return [
            parse_comment(
                comentario,
                postagem_url,
            )
            for comentario in comentarios_brutos
        ]

    def _resolve_ids(
        self,
        postagem_url: str,
        user_id: str | None,
    ) -> tuple[str, str]:
        """
        Resolve photo_id e user_id.

        Aceita URL completa ou photo_id puro.

        Quando somente o photo_id for informado,
        user_id também precisa ser fornecido.
        """
        valor = postagem_url.strip()

        if not valor:
            raise ValueError("Postagem não pode ser vazia.")

        if valor.isdigit():
            if user_id is None:
                raise ValueError(
                    "Ao informar somente o photo_id, também informe o user_id."
                )

            user_id_limpo = user_id.strip().removeprefix("@")

            if not user_id_limpo:
                raise ValueError("user_id não pode ser vazio.")

            return (
                valor,
                user_id_limpo,
            )

        ids = extract_ids_from_url(valor)

        if ids is None:
            raise ValueError(f"URL inválida: {postagem_url}")

        photo_id, url_user_id = ids

        if user_id is not None and user_id.strip():
            resolved_user_id = user_id.strip().removeprefix("@")
        else:
            resolved_user_id = url_user_id

        if not resolved_user_id or resolved_user_id == "unknown":
            raise ValueError("Não foi possível identificar o user_id da postagem.")

        return (
            photo_id,
            resolved_user_id,
        )

    def _validar_auth_provider_live(
        self,
    ) -> None:
        """
        Impede uma chamada HTTP real quando o provider
        criado pela aplicação não possui uma fonte de
        autenticação configurada.

        Providers customizados/fakes continuam permitidos,
        preservando injeção de dependência e testes.
        """
        if self.auth_provider is None:
            raise RuntimeError(
                "Autenticação mobile não configurada. "
                "Configure um provider autorizado antes "
                "de realizar coleta em tempo real."
            )

        provider: object = self.auth_provider

        if isinstance(
            provider,
            AndroidProfileMobileRequestProvider,
        ):
            provider = provider.delegate

        if (
            isinstance(provider, ConfiguredMobileRequestProvider)
            and provider.signature_service is None
        ):
            raise RuntimeError(
                "Autenticação mobile não configurada. "
                "O perfil Android está pronto, mas não "
                "existe uma fonte válida de autenticação. "
                "Configure KWAI_MOBILE_AUTH_ENDPOINT "
                "ou forneça um serviço autorizado "
                "de assinatura."
            )

    def _get_comments_live(
        self,
        postagem_url: str,
        max_comments: int | None,
        user_id: str | None,
    ) -> list[Comentario]:
        """
        Coleta comentários em tempo real.

        max_comments:
            int  -> limita a quantidade.
            None -> coleta todas as páginas
                    até o servidor indicar o fim.
        """
        self._validar_auth_provider_live()

        resume: CommentCollectionProgress | None = None
        if self.resume_collection:
            if self.checkpoint_path is None:
                raise ValueError(
                    "Informe o arquivo de progresso para retomar a coleta."
                )
            resume = load_comment_checkpoint(self.checkpoint_path)

        photo_id, resolved_user_id = self._resolve_ids(
            postagem_url,
            resume.user_id if resume is not None and user_id is None else user_id,
        )

        def save_progress(progress: CommentCollectionProgress) -> None:
            if self.checkpoint_path is not None:
                save_comment_checkpoint(progress, self.checkpoint_path)

        if self.live_client is None:
            self.live_client = LiveCommentClient(
                auth_provider=(self.auth_provider),
                max_attempts=self.max_attempts,
                backoff_base=self.backoff_base,
                page_delay=self.page_delay,
            )

        try:
            comentarios_brutos = self.live_client.fetch_root_comments(
                photo_id=photo_id,
                user_id=resolved_user_id,
                max_comments=max_comments,
                resume=resume,
                on_progress=(
                    save_progress if self.checkpoint_path is not None else None
                ),
            )
        except CommentCollectionInterrupted as exc:
            save_progress(exc.progress)
            raise

        if max_comments is not None and len(comentarios_brutos) < max_comments:
            logger.warning(
                "Solicitados %d comentários; obtidos %d.",
                max_comments,
                len(comentarios_brutos),
            )

        return [
            parse_comment(
                comentario,
                postagem_url,
            )
            for comentario in comentarios_brutos
        ]

    def get_comments(
        self,
        postagem_url: str,
        max_comments: int | None = None,
        *,
        user_id: str | None = None,
    ) -> list[Comentario]:
        """
        Retorna comentários do Kwai.

        Quando arquivo_json é informado,
        utiliza páginas salvas localmente.

        Caso contrário, utiliza o cliente
        mobile em tempo real.

        O mecanismo de autenticação é recebido
        por injeção através de auth_provider.

        max_comments:
            int  -> limita a quantidade.
            None -> coleta todos os comentários.
        """
        if self.arquivo_json is not None:
            return self._get_comments_from_file(
                postagem_url,
                max_comments,
            )

        return self._get_comments_live(
            postagem_url,
            max_comments,
            user_id,
        )

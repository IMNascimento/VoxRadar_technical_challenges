[⬅️ Voltar ao índice principal](../README.md)

# 🔀 Fluxos e pipelines

O conteúdo do antigo `docs/flows.md` está distribuído por responsabilidade.
Os diagramas representam a implementação síncrona atual; não há workers, banco,
fila ou signer externo oculto no fluxo.

| Fluxo | Entrada → saída | Relacionados |
|---|---|---|
| [Ciclo de vida](./runtime.md) | CLI/Python → serviços → serialização e fechamento. | Todas as operações. |
| [Busca](./search.md) | Palavras-chave → lista de `Post`. | UC-001. |
| [Perfil](./profile.md) | Handle → id → páginas → lista de `Post`. | UC-002. |
| [Comentários](./comments.md) | URL → raízes → expansão opcional. | UC-003. |
| [Paginação e interrupção](./pagination.md) | Cursor → páginas → fim ou erro/parcial. | Perfil, raízes e sublistas. |

Fontes: `src/application/`, `src/container.py` e adapters em `src/infrastructure/`.
HTTP e transformação em modelos pertencem aos adapters; limites e dedupe,
aos casos de uso. Veja [Arquitetura](../internals/architecture.md),
[Regras](../business-rules/README.md) e [Casos de uso](../use-cases/README.md).

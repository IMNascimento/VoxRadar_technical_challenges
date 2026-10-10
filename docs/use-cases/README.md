[⬅️ Voltar ao índice principal](../README.md)

# 🎯 Casos de uso

| Caso | Entrada | Saída normal | Serviço Python |
|---|---|---|---|
| [UC-001 — Buscar postagens](./uc-001-search-posts.md) | Palavras-chave e limite total. | `CollectionResult` de `Post`. | `services.search_posts`. |
| [UC-002 — Coletar perfil](./uc-002-collect-user-posts.md) | Handle e limite opcional. | `CollectionResult` de `Post` (e comentários opcionais). | `services.profile_bundle`. |
| [UC-003 — Coletar comentários](./uc-003-collect-comments.md) | URL, limite de raízes e expansão opcional. | `CollectionResult` de `Comment` ou `ExpandedComment`. | `services.comment_versions`. |

Os casos descrevem comportamento observável, não uma lista de endpoints. A
referência de assinaturas e imports está em [API Python](../reference/api-reference.md).
A entrada é validada ao criar o comando (`src.application.dtos.commands`), antes de
qualquer requisição; a CLI também valida limites positivos. Resultado parcial é uma falha sinalizada, não sucesso completo.

Relacionados: [Regras](../business-rules/README.md), [Fluxos](../flows/README.md),
[Schemas](../reference/schemas.md), [ADRs](../adr/README.md).

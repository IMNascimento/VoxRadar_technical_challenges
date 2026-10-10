[⬅️ Voltar ao índice principal](../README.md)

# 🎯 Casos de uso

| Caso | Entrada | Saída normal | Função Python |
|---|---|---|---|
| [UC-001 — Buscar postagens](./uc-001-search-posts.md) | Palavras-chave e limite total. | Lista de `Post`. | `scraper.search_posts`. |
| [UC-002 — Coletar perfil](./uc-002-collect-user-posts.md) | Usuário e limite opcional. | Lista de `Post`. | `scraper.get_user_posts`. |
| [UC-003 — Coletar comentários](./uc-003-collect-comments.md) | URL, limite e respostas opcionais. | Lista de `Comment` ou `CommentWithReplies`. | `scraper.get_comments`. |

São as três funcionalidades exigidas pelo desafio. Os casos descrevem o
comportamento observável, não uma lista de endpoints. Assinaturas e imports
estão na [Referência Python](../reference/api-reference.md).

A entrada é validada antes de qualquer requisição; a CLI também valida limites
positivos. Se a coleta falhar no meio, o resultado é descartado: não existe
sucesso parcial.

Relacionados: [Regras](../business-rules/README.md), [Fluxos](../flows/README.md),
[Schemas](../reference/schemas.md), [ADRs](../adr/README.md).

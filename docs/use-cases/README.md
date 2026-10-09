[⬅️ Voltar ao índice principal](../README.md)

# 🎯 Casos de uso

| Caso | Entrada | Saída normal | Serviço Python |
|---|---|---|---|
| [UC-001 — Buscar postagens](./uc-001-search-posts.md) | Palavras-chave e limite total. | Lista de `Post`. | `services.search_posts`. |
| [UC-002 — Coletar perfil](./uc-002-collect-user-posts.md) | Handle e limite opcional. | Lista de `Post`. | `services.user_posts`. |
| [UC-003 — Coletar comentários](./uc-003-collect-comments.md) | URL, limite de raízes e expansão opcional. | Lista de `Comment` ou `ExpandedComment`. | `services.comments`. |

Os casos descrevem comportamento observável, não uma lista de endpoints. A
referência de assinaturas e imports está em [API Python](../reference/api-reference.md).
Os limites positivos são validados pela CLI; integrações Python devem passá-los
corretamente. Resultado parcial é uma falha sinalizada, não sucesso completo.

Relacionados: [Regras](../business-rules/README.md), [Fluxos](../flows/README.md),
[Schemas](../reference/schemas.md), [ADRs](../adr/README.md).

[⬅️ Voltar ao índice principal](../README.md)

# ⚖️ Regras de negócio e políticas de coleta

Estas regras descrevem o comportamento implementado, não regras internas do
Kwai nem requisitos novos. A seção inclui políticas da aplicação e do contrato
de saída: elas não estão necessariamente implementadas em `domain/`.

| Documento | Regras | Conteúdo |
|---|---|---|
| [Coleta](./collection.md) | RN-001 a RN-006 | Fontes, limites, dedupe, paginação e expansão. |
| [Contrato de dados](./data-contract.md) | RN-007 a RN-010 | Tipos de saída, valores desconhecidos, timestamps e total declarado. |
| [Falhas e resultado parcial](./failure-policy.md) | RN-011 a RN-015 | Retry, rejeição de páginas, interrupção, loops e escrita. |

Cada regra informa condição, consequência, implementação e limites. “Motivação”
explica o efeito da política no coletor; não atribui intenção ao servidor ou
justificativa histórica não registrada. Limitações permissivas do mapper
continuam descritas em [Schemas](../reference/schemas.md).

Relacionados: [Fluxos](../flows/README.md), [Casos de uso](../use-cases/README.md)
e [ADRs](../adr/README.md).

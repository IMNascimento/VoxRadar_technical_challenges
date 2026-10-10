[⬅️ Voltar ao índice principal](../README.md)

# ⚖️ Regras de negócio e políticas de coleta

Estas regras descrevem o comportamento implementado, não regras internas do
Kwai nem requisitos novos. Elas cobrem as políticas da coleta, do contrato de
saída e do tratamento de falhas.

| Documento | Regras | Conteúdo |
|---|---|---|
| [Coleta](./collection.md) | RN-001 a RN-007 | Fontes, limites, deduplicação, fim de paginação e respostas. |
| [Contrato de dados](./data-contract.md) | RN-008 a RN-011 | Modelos de saída, valores desconhecidos, datas e total declarado. |
| [Falhas e saída](./failure-policy.md) | RN-012 a RN-016 | Validação da entrada, retry, erro de negócio, saída tudo ou nada e códigos de saída. |

Cada regra informa condição, consequência, implementação, exceções e testes.
“Motivação” explica o efeito da política no coletor; não atribui intenção ao
servidor do Kwai. Limitações permissivas do parser continuam descritas em
[Schemas](../reference/schemas.md).

Relacionados: [Fluxos](../flows/README.md), [Casos de uso](../use-cases/README.md)
e [ADRs](../adr/README.md).

[⬅️ ADRs](./README.md) · [🏠 Índice](../README.md)

# ADR-0005 — Entidades do domínio como contrato de saída

| | |
|---|---|
| **Status** | ✅ Aceita — adotada no código examinado. |
| **Data** | 2026-10-09 — registro retrospectivo, não data original comprovada. |
| **Escopo** | `Post`, `Comment`, `ExpandedComment` e a exportação JSON da CLI. |

## Contexto

O desafio fixa o schema de saída (`Postagem` e `Comentario`), com nomes de
campo em português e campos obrigatórios definidos. O coletor não tem regra de
negócio além de identidade, deduplicação, paginação e ordenação: os itens são
criados pelo mapeamento da API, ordenados e exportados sem mudar de estado.

A convenção DDD de referência pede que entidades não saiam da aplicação e que
DTOs façam a ponte com o mundo externo.

## Alternativas

**A — DTOs de saída em `application/dtos`, mapeados a partir das entidades:**
isola o domínio do formato JSON, mas duplica `Post`, `Comment`, autores e
engajamento campo a campo, com um mapeamento que só copia valores.

**B — Entidades como contrato de saída:** um único modelo para mapear, ordenar
e serializar; o domínio passa a refletir o schema do desafio.

## Decisão

Adotar **B**. `domain/entities` define `Post`, `Comment` e a extensão opt-in
`ExpandedComment` exatamente no formato do schema. `CollectionResult` carrega
essas entidades até a CLI, que as serializa com `dataclasses.asdict()`.

`ExpandedComment` fica no domínio junto de `Comment`, porque estende o mesmo
contrato com o vínculo de resposta; ele não substitui `Comment` quando a coleta
não pede respostas.

## Trade-offs

- **Ganhamos:** um só modelo, sem mapeamento de cópia; o schema do desafio é
  verificável lendo as entidades.
- **Abrimos mão de:** isolamento entre domínio e apresentação. Mudar o contrato
  JSON (renomear, aninhar ou omitir campo) mexe em `domain/entities`.
- **Custo:** os campos das entidades são primitivos do schema (`str`, `int`),
  não value objects; `id` é opcional porque a API pode omiti-lo. Comportamento
  que não altera o contrato fica na própria entidade como propriedade ou método
  (`dedup_key`, `Engagement.count`), porque `asdict()` só serializa campos.
- **Risco:** um segundo formato de saída (CSV, API HTTP, outro schema) tentaria
  adaptar o domínio a ele.
- **Revisitar quando:** surgir um segundo formato de saída, uma regra que mude o
  estado de uma postagem ou comentário, ou um contrato que diverja do modelo
  interno. Nesse ponto, introduzir DTOs de saída em `application/dtos`.

## Consequências e verificação

A CLI depende das entidades do domínio para tipar e serializar resultados; essa
é a única dependência de `entrypoints` em `domain/entities`. O mapeamento de
campos externos continua só em `src/infrastructure/kwai/mapping.py`.

Implementação: `src/domain/entities/`, `src/application/dtos/collection_result.py`,
`src/entrypoints/cli/export_files.py`. Testes: `tests/unit/test_models.py`,
`tests/unit/test_samples.py`, `tests/integration/test_cli_exports.py`.

[Contrato de dados](../business-rules/data-contract.md) ·
[Schemas](../reference/schemas.md) · [Arquitetura](../internals/architecture.md).

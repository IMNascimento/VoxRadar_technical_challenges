[⬅️ ADRs](./README.md) · [🏠 Índice](../README.md)

# ADR-0005 — Modelos Pydantic como contrato de saída

| | |
|---|---|
| **Status** | ✅ Aceita — adotada no código atual. |
| **Data** | 2026-10-09 — registro retrospectivo. |
| **Escopo** | `Post`, `Comment`, `CommentWithReplies` e a serialização da CLI. |

## Contexto

O desafio fixa os schemas `Postagem` e `Comentario`, com nomes de campo em
português e campos obrigatórios. O nível 1 pede modelos que validem o contrato
de saída e recomenda validar com Pydantic. A configuração já usa
`pydantic-settings`, que depende do Pydantic.

## Alternativas

**A — Dicionários:** zero dependência e nenhum código de modelo, mas nenhum
contrato verificável e nenhuma checagem de tipo.

**B — Dataclasses:** contrato declarado e tipado para o mypy, mas sem validação
em tempo de execução dos tipos e do formato das datas.

**C — Modelos Pydantic:** validam tipos, obrigatórios e formato no construtor e
serializam com `model_dump()`.

## Decisão

Adotar **C**. [`models.py`](../../kwai_collector/models.py) define os modelos no
formato exato dos schemas, com o padrão `ISO_DATE` nas datas.
`CommentWithReplies` herda de `Comment` e acrescenta os campos de vínculo; ele
só aparece com `--with-replies`.

## Trade-offs

- **Ganhamos:** o JSON gerado é validado na criação de cada item; as amostras
  podem ser validadas com `model_validate` nos testes; o contrato fica legível
  num único arquivo.
- **Abrimos mão de:** isolamento entre o formato interno e o JSON; mudar o
  contrato é mudar os modelos.
- **Custo:** um dado inesperado que não caiba no modelo gera `ValidationError`,
  que a CLI não converte em mensagem amigável. Campos extras passados ao
  construtor são ignorados, não rejeitados.
- **Revisitar quando:** surgir um segundo formato de saída ou um contrato que
  divirja do modelo interno.

## Consequências e verificação

O parser monta os modelos; a CLI só chama `model_dump()`. Testes:
`tests/test_parser.py` (`test_modelo_rejeita_data_fora_do_padrao`) e
`tests/test_samples.py`.

[Contrato de dados](../business-rules/data-contract.md) · [Schemas](../reference/schemas.md).

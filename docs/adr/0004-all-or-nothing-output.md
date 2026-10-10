[⬅️ ADRs](./README.md) · [🏠 Índice](../README.md)

# ADR-0004 — Saída tudo ou nada, sem resultado parcial

| | |
|---|---|
| **Status** | ✅ Aceita — adotada no código atual. |
| **Data** | 2026-10-09 — registro retrospectivo. |
| **Escopo** | Comportamento dos três comandos quando a coleta falha no meio. |

## Contexto

Uma coleta paginada pode falhar depois de várias páginas: rede, erro de negócio
ou mudança de formato. O contrato JSON do desafio é uma lista simples, sem
envelope para dizer se ela está completa. O projeto prioriza o menor código
que resolve as três funcionalidades.

## Alternativas

**A — Preservar o parcial:** carregar os itens já coletados numa exceção,
gravar um arquivo marcado como parcial e sair com erro. Aproveita o dado, mas
exige uma exceção própria, uma convenção de nome de arquivo e disciplina do
consumidor para não tratar o parcial como completo.

**B — Gravar a cada página:** nunca perde progresso, mas o arquivo fica
incompleto durante a coleta e exige escrita incremental ou JSONL.

**C — Tudo ou nada:** coletar tudo em memória e só escrever no fim; qualquer
falha descarta o que foi coletado.

## Decisão

Adotar **C**. `collect_and_save` só serializa depois de a função do scraper
retornar. Em `InvalidInput` sai com `2`; em `KwaiError`, com `1`; em nenhum dos
casos grava ou imprime JSON.

## Trade-offs

- **Ganhamos:** um arquivo que existe está sempre completo do ponto de vista do
  coletor; nenhum código de parcial para manter; o arquivo antigo no destino
  fica intacto se a nova coleta falhar.
- **Abrimos mão de:** aproveitar o progresso. Uma falha na última página de um
  perfil com milhares de posts descarta minutos de coleta.
- **Custo:** a lista inteira fica em memória até o fim. Não há checkpoint nem
  retomada.
- **Revisitar quando:** coletas longas falharem com frequência, ou o consumidor
  precisar de retomada ou escrita incremental.

## Consequências e verificação

O retry com backoff e a troca de host reduzem a chance de falha tardia, mas não
a eliminam. Para coletas grandes, use `--limit` ou aumente `KWAI_MAX_RETRIES`.

Implementação: `collect_and_save` em [`cli.py`](../../kwai_collector/cli.py).
Teste: `tests/test_cli.py` (`test_erro_de_rede_sai_com_1`).

[RN-015](../business-rules/failure-policy.md#rn-015--saída-tudo-ou-nada) ·
[Paginação](../flows/pagination.md) · [CLI](../guides/cli.md#falhas-e-códigos-de-saída).

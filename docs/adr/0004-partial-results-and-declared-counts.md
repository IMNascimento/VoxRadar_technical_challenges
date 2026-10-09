[⬅️ ADRs](./README.md) · [🏠 Índice](../README.md)

# ADR-0004 — Preservar parcial e distinguir declarado de coletado

| | |
|---|---|
| **Status** | ✅ Aceita — políticas adotadas no código examinado. |
| **Data** | 2026-10-08 — registro retrospectivo, não data original comprovada. |
| **Escopo** | Interrupções, loops de sublista e contagem de respostas. |

## Contexto

Uma falha posterior não deve ocultar os itens já coletados nem virar sucesso
silencioso. A API pode declarar um total diferente das respostas entregues;
o alvo observado declarou 59 e entregou 52 com fim de cursor, sem causa determinada.
O contrato JSON não possui envelope de completude/erro.

## Alternativas

**A — Descartar todo resultado na falha:** simplifica o sinal de sucesso/erro,
mas perde itens válidos de páginas/unidades anteriores.

**B — Retornar lista truncada como sucesso ou pular itens inválidos de comentário:**
mantém uma saída aparente, mas oculta a interrupção e pode mascarar perda.

**C — Preservar parcial com erro explícito; contagens divergentes como warning:**
permite aproveitar o dado sem afirmar causa/completude. Exige disciplina do consumidor.

## Decisão

Quando uma falha coberta interrompe um caso de uso com itens, lançar
`CollectionInterruptedError` com `partial` e causa original. CLI tenta escrever
essa lista e sai com `1`; sem itens, propaga erro sem nova saída.

Manter recuperação local para loop de sublista: warning e próxima raiz. Outra
falha de sublista interrompe com respostas lidas e raízes pendentes preservadas.
Não rejeitar a coleta só pela diferença numérica; conservar o total declarado
e avisar quantidade única entregue com causa não determinada.

## Trade-offs

- **Ganhamos:** itens anteriores aproveitáveis, erro rastreável, diagnóstico de
  contagem sem inventar sete respostas ou uma causa para a divergência.
- **Abrimos mão de:** interpretação da lista JSON sozinha como “coleta completa”;
  o consumidor precisa acompanhar exit code, exceção e warnings.
- **Custo:** listas ficam em memória por unidade; parcial não é checkpoint
  ou retomada. A CLI nova publica JSON por rename, mas não há transação do
  conjunto. Falha de escrita ainda pode impedir persistência de uma unidade.
- **Risco:** confundir raiz pendente de expansão com raiz comprovadamente sem
  respostas; `respostas_total` continua declarado, inclusive no parcial.
- **Revisitar quando:** o consumidor exigir retomada, escrita a cada página ou
  sinal de completude no próprio contrato. Alterar o JSON demanda decisão
  explícita; não inserir envelope silenciosamente.

## Consequências e verificação

Páginas de comentários com item inválido são rejeitadas inteiras, sem descartar
páginas anteriores. Quantidade desconhecida/negativa não gera comparação.
Exit `0` pode coexistir com warning de discrepância, sem significar completude.

Implementação: `src/application/exceptions.py`, `collect_comments.py`,
`src/entrypoints/cli.py`. Testes: `tests/test_usecases.py`,
`tests/test_response_validation.py`, `tests/test_cli.py`.

[RN-010](../business-rules/data-contract.md#rn-010--total-declarado-não-significa-completude) ·
[RN-012 a RN-015](../business-rules/failure-policy.md) ·
[Comentários](../flows/comments.md) · [UC-003](../use-cases/uc-003-collect-comments.md).

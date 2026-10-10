[⬅️ ADRs](./README.md) · [🏠 Índice](../README.md)

# ADR-0006 — Saída num arquivo único ou no stdout

| | |
|---|---|
| **Status** | ✅ Aceita — adotada no código atual. |
| **Data** | 2026-10-09 — registro retrospectivo. |
| **Escopo** | Opção `--out` dos três comandos. |

## Contexto

O exemplo de CLI do desafio usa `--out out/busca.json`: um caminho de arquivo
por funcionalidade. Cada comando produz uma única lista JSON.

## Alternativas

**A — Pasta por execução:** criar `<base>/<dono>/<data-hora>/` com um arquivo
por tipo de dado. Guarda o histórico de execuções, mas exige gerar nomes,
tratar caracteres inválidos e explicar ao usuário onde o arquivo foi parar.

**B — Arquivo único ou stdout:** `--out` é o caminho do arquivo; sem ele, o
JSON vai para o stdout.

## Decisão

Adotar **B**. `collect_and_save` cria as pastas do caminho, grava em UTF-8 e
sobrescreve o arquivo existente. Sem `--out`, usa `typer.echo`. Os logs vão
sempre para o stderr, então o stdout contém só o JSON.

## Trade-offs

- **Ganhamos:** o mesmo formato do exemplo do desafio, saída previsível e
  composição com outras ferramentas por redirecionamento.
- **Abrimos mão de:** histórico automático; rodar de novo com o mesmo `--out`
  apaga o resultado anterior.
- **Custo:** o usuário escolhe e organiza os nomes dos arquivos. No Windows
  PowerShell 5.1, redirecionar com `>` grava em UTF-16; `--out` evita isso.
- **Revisitar quando:** for preciso guardar várias execuções do mesmo alvo ou
  gerar mais de um arquivo por comando.

## Consequências e verificação

Implementação: `collect_and_save` em [`cli.py`](../../kwai_collector/cli.py).
Testes: `tests/test_cli.py` (`test_search` grava num arquivo temporário; os
demais leem o stdout).

[RN-016](../business-rules/failure-policy.md#rn-016--códigos-de-saída-e-escrita) ·
[CLI](../guides/cli.md#destino-da-saída).

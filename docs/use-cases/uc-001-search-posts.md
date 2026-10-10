[⬅️ Casos de uso](./README.md) · [🏠 Índice](../README.md)

# 🎯 UC-001 — Buscar postagens por palavra-chave

| | |
|---|---|
| **Ator** | Usuário da CLI ou programa Python chamador. |
| **Objetivo** | Obter postagens associadas a uma ou mais palavras-chave, sem login implementado. |
| **Pré-condições** | Dependências instaladas, configuração válida, acesso HTTPS ao Kwai e lista de palavras não vazia. |
| **Entrada** | `SearchCommand.create(keywords, *, limit=20, sort_by=None)`; na CLI, `--keyword/-k` repetível e `--limit/-l`. |
| **Implementação** | `src/application/use_cases/search_posts.py`, injetado com `ISearchApiPort`. |
| **Saída** | `list[Post]`, ordenada pela primeira ocorrência, limitada após dedupe. |

## Fluxo principal

1. Receber palavras e limite positivo; CLI monta serviços com `Settings`.
2. Validar que a lista não está vazia e gerar o carimbo `coletado_em`.
3. Definir `count` entre 1 e 50 a partir do limite total; é o tamanho da página.
4. Consultar uma página da palavra na API web, com `pcursor` começando em `0`;
   o adapter devolve os modelos e o deslocamento da próxima página.
5. Acumular postagens únicas por id truthy ou URL.
6. Se a página trouxe post novo e o teto não foi atingido, pedir a próxima
   página; senão, seguir para outra palavra, se houver.
7. Devolver a lista fatiada ao limite. `search` grava `posts.json` na pasta da
   execução antes de fechar clientes.

## Fluxos alternativos

- **2a — Lista vazia:** `InvalidInputError`; a CLI sinaliza entrada inválida.
- **4a — Transporte transitório:** repetir no mesmo servidor conforme configuração.
- **4b — Erro de negócio:** interromper sem retry de negócio.
- **4c — Página sem post novo:** a palavra se esgotou (a API repete itens em vez
  de devolver lista vazia); segue para outra palavra, sem erro.
- **4d — Feed inválido:** mapper aplica sua política de descarte/rejeição; consultar Schemas.
- **4e — Falha com itens de palavras anteriores:** `CollectionInterruptedError`
  preserva esses itens; palavras seguintes não são consultadas.
- **7a — Escrita falha:** a CLI trata `OSError` e sinaliza exit `1`; não há garantia de arquivo íntegro.

## Pós-condições e limites

- Sucesso não prova correspondência exaustiva de toda a plataforma à palavra.
- O `count` não diminui conforme o saldo entre palavras.
- A API Python não valida internamente `limit >= 1`; esse é o contrato de uso
  documentado, imposto na CLI.

## Verificação

| Área | Testes |
|---|---|
| Limite, dedupe, vazio e erro de outra palavra | `tests/unit/test_usecases.py`. |
| HTTP, retry e negócio | `tests/integration/test_collector.py`. |
| Argumentos, saída e parcial | `tests/integration/test_cli.py`. |

## Relacionados

[Fluxo de busca](../flows/search.md) · [Ciclo de vida](../flows/runtime.md) ·
[RN-001, RN-002 e RN-004](../business-rules/collection.md) ·
[RN-011, RN-013 e RN-015](../business-rules/failure-policy.md) · [Schemas](../reference/schemas.md).

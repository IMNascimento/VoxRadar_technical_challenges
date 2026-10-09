[⬅️ Casos de uso](./README.md) · [🏠 Índice](../README.md)

# 🎯 UC-001 — Buscar postagens por palavra-chave

| | |
|---|---|
| **Ator** | Usuário da CLI ou programa Python chamador. |
| **Objetivo** | Obter postagens associadas a uma ou mais palavras-chave, sem login implementado. |
| **Pré-condições** | Dependências instaladas, configuração válida, acesso HTTPS ao Kwai e lista de palavras não vazia. |
| **Entrada** | `keywords: list[str]`, `limit: int = 20`; na CLI, `--keyword/-k` repetível e `--limit/-l`. |
| **Implementação** | `src/application/search_posts.py`, injetado com `SearchApiPort`. |
| **Saída** | `list[Post]`, ordenada pela primeira ocorrência, limitada após dedupe. |

## Fluxo principal

1. Receber palavras e limite positivo; CLI monta serviços com `Settings`.
2. Validar que a lista não está vazia e gerar o carimbo `coletado_em`.
3. Definir `count` entre 1 e 50 a partir do limite total.
4. Consultar uma palavra na API web; adapter devolve modelos do lote.
5. Acumular postagens únicas por id truthy ou URL.
6. Repetir para outra palavra se houver e o teto não tiver sido atingido.
7. Devolver a lista fatiada ao limite. `search` grava `posts.json` na pasta da
   execução antes de fechar clientes.

## Fluxos alternativos

- **2a — Lista vazia:** `InvalidInputError`; a CLI sinaliza entrada inválida.
- **3a — Limite > 50:** registrar warning e pedir 50 por palavra; não paginar essa palavra.
- **4a — Transporte transitório:** repetir no mesmo servidor conforme configuração.
- **4b — Erro de negócio:** interromper sem retry de negócio.
- **4c — Lote vazio:** pode continuar para outra palavra; não declara quebra automaticamente.
- **4d — Feed inválido:** mapper aplica sua política de descarte/rejeição; consultar Schemas.
- **4e — Falha com itens de palavras anteriores:** `CollectionInterruptedError`
  preserva esses itens; palavras seguintes não são consultadas.
- **7a — Escrita falha:** a CLI trata `OSError` e sinaliza exit `1`; não há garantia de arquivo íntegro.

## Pós-condições e limites

- Sucesso não prova correspondência exaustiva de toda a plataforma à palavra.
- O `count` não diminui conforme o saldo entre palavras.
- `pcursor=0` no payload não significa paginação implementada.
- A API Python não valida internamente `limit >= 1`; esse é o contrato de uso
  documentado, imposto na CLI.

## Verificação

| Área | Testes |
|---|---|
| Limite, dedupe, vazio e erro de outra palavra | `tests/test_usecases.py`. |
| HTTP, retry e negócio | `tests/test_collector.py`. |
| Argumentos, saída e parcial | `tests/test_cli.py`. |

## Relacionados

[Fluxo de busca](../flows/search.md) · [Ciclo de vida](../flows/runtime.md) ·
[RN-001, RN-002 e RN-004](../business-rules/collection.md) ·
[RN-011, RN-013 e RN-015](../business-rules/failure-policy.md) · [Schemas](../reference/schemas.md).

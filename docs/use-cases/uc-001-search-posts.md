[⬅️ Casos de uso](./README.md) · [🏠 Índice](../README.md)

# 🎯 UC-001 — Buscar postagens por palavra-chave

| | |
|---|---|
| **Ator** | Usuário da CLI ou programa Python chamador. |
| **Objetivo** | Obter postagens relacionadas a uma ou mais palavras-chave, com link, texto e engajamento, sem login. |
| **Pré-condições** | Dependências instaladas, configuração válida, acesso HTTPS ao Kwai e ao menos uma palavra-chave não vazia. |
| **Entrada** | `search_posts(keywords, limit=20)`; na CLI, `--keyword/-k` repetível e `--limit/-l`. |
| **Implementação** | `search_posts` em [`scraper.py`](../../kwai_collector/scraper.py). |
| **Saída** | `list[Post]` na ordem da primeira ocorrência, com no máximo `limit` itens. |

## Fluxo principal

1. Receber as palavras e o limite; a CLI exige `limit >= 1`.
2. Descartar palavras em branco e gerar o carimbo `coletado_em`.
3. Calcular `count = min(limit, 50)`, o tamanho de cada página.
4. Consultar uma página da palavra na API web, com `pcursor` começando em `0`,
   e converter os feeds em `Post`.
5. Acumular postagens com `id` ainda não visto.
6. Se a página trouxe post novo e o limite não foi atingido, avançar o
   `pcursor` em `count` e voltar ao passo 4; senão, seguir para a próxima
   palavra, se houver e se o limite não foi atingido.
7. Devolver a lista cortada no limite; a CLI grava ou imprime o JSON.

## Fluxos alternativos

- **2a — Nenhuma palavra válida:** `InvalidInput`; a CLI sai com `2`.
- **4a — Falha passageira:** repetir no mesmo host conforme `max_retries`.
- **4b — Erro de negócio ou status de erro não passageiro:** `KwaiError`, sem retry.
- **4c — Página sem post novo:** a palavra se esgotou (a API repete itens em
  vez de devolver lista vazia); segue para a próxima palavra, sem erro.
- **4d — Feed sem id ou usuário:** ignorado com warning; os demais seguem.
- **4e — Falha depois de palavras já consultadas:** os itens anteriores são
  descartados; a CLI sai com `1`.
- **7a — Escrita falha:** a CLI registra o erro e sai com `1`.

## Pós-condições e limites

- Sucesso não prova que toda a plataforma foi pesquisada para a palavra.
- O `count` não diminui conforme o saldo entre palavras.
- A função Python não valida `limit >= 1`; essa validação é da CLI.

## Verificação

| Área | Testes |
|---|---|
| Comando, JSON e limite | `tests/test_cli.py` (`test_search`). |
| Paginação e parada sem post novo | `tests/test_cli.py` (`test_search_pagina_ate_nao_vir_post_novo`). |
| Falha de rede e exit `1` | `tests/test_cli.py` (`test_erro_de_rede_sai_com_1`). |
| Retry e erro de negócio na web | `tests/test_client.py`. |
| Conversão do feed de busca | `tests/test_parser.py` (`test_parse_post_da_busca`). |

## Relacionados

[Fluxo de busca](../flows/search.md) · [Ciclo de vida](../flows/runtime.md) ·
[RN-001, RN-002 e RN-005](../business-rules/collection.md) ·
[RN-012 a RN-016](../business-rules/failure-policy.md) · [Schemas](../reference/schemas.md).

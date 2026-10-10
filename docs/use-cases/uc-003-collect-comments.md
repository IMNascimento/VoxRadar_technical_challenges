[⬅️ Casos de uso](./README.md) · [🏠 Índice](../README.md)

# 🎯 UC-003 — Coletar comentários e respostas

| | |
|---|---|
| **Ator** | Usuário da CLI ou programa Python chamador. |
| **Objetivo** | Obter os comentários de uma postagem a partir do link e, opcionalmente, as respostas com vínculo explícito. |
| **Pré-condições** | Configuração válida, acesso HTTPS aos hosts móveis e URL com `/video/<id>` ou `/photo/<id>`. |
| **Entrada** | `get_comments(post_url, limit=None, with_replies=False)`; na CLI, `comments --url`, `--limit/-l` e `--with-replies`. |
| **Implementação** | `get_comments`, `get_root_comments` e `get_replies` em [`scraper.py`](../../kwai_collector/scraper.py). |
| **Saída** | `list[Comment]`; com respostas, lista plana de `CommentWithReplies`. |

## Fluxo principal

1. Extrair o id da URL e gerar `coletado_em`.
2. Paginar os comentários principais com `count=50`.
3. Deduplicar e parar ao atingir o limite de comentários únicos, guardando o
   total de respostas declarado de cada um.
4. Sem respostas, devolver os `Comment`.
5. Com respostas, percorrer os principais na ordem e acrescentar cada um como
   `CommentWithReplies` com `respostas_total`.
6. Se o principal for elegível, paginar a sublista com `count=100` e
   acrescentar as respostas novas logo depois dele, com `parent_id`,
   `reply_to_id` e `reply_to_usuario`.
7. Devolver a lista; a CLI grava ou imprime o JSON.

## Fluxos alternativos

- **1a — URL sem id:** `InvalidInput`, exit `2`. O host da URL não é conferido.
- **2a — Post inexistente:** a API costuma devolver lista vazia; o resultado é
  `[]` com exit `0`.
- **2b — Comentários repetidos entre páginas:** só a primeira ocorrência entra
  e só ela conta para o limite.
- **6a — Principal sem id ou com total `None`/zero:** não consulta a sublista.
- **6b — Total negativo:** a regra usa truthiness e consulta a sublista.
- **6c — Cursor de sublista repetido:** warning e fim das respostas daquele
  principal; segue para o próximo.
- **6d — Resposta igual a um item já incluído:** descartada.
- **6e — Qualquer falha de rede ou da API:** descarta tudo; exit `1`.

## Pós-condições e limites

- O limite não controla a quantidade de respostas nem o volume total.
- `parent_id` aponta para o comentário principal; `reply_to_id` aponta para um
  **usuário**.
- `respostas_total` é o que a API declara, não o tamanho da lista de respostas.
  O coletor não avisa quando os dois diferem.
- Fim de cursor não comprova completude. Prévias embutidas não são usadas.

## Verificação

| Área | Testes |
|---|---|
| Principais, respostas, vínculos e `respostas_total` | `tests/test_cli.py` (`test_comments_com_respostas`). |
| URL inválida e exit `2` | `tests/test_cli.py` (`test_url_invalida_sai_com_2`). |
| Conversão de comentário e HTML | `tests/test_parser.py` (`test_parse_comment`, `test_texto_com_html_escapado`). |
| Troca de host e assinatura no corpo | `tests/test_client.py`. |

## Relacionados

[Fluxo de comentários](../flows/comments.md) · [Paginação](../flows/pagination.md) ·
[RN-004 a RN-007](../business-rules/collection.md) ·
[RN-008 e RN-011](../business-rules/data-contract.md) ·
[RN-012 a RN-016](../business-rules/failure-policy.md).

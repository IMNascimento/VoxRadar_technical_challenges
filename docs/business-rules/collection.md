[⬅️ Regras de negócio](./README.md) · [🏠 Índice](../README.md)

# ⚖️ Coleta

## RN-001 — Fonte por operação

- **Regra:** a busca usa a API web (`www.kwai.com`); perfil, comentários e
  respostas usam a API móvel. Não há troca automática de superfície depois de
  uma falha.
- **Motivação:** usar, para cada operação, o caminho que entrega os dados sem
  login, navegador ou assinador externo.
- **Implementada em:** `post_web` e `post_mobile` em
  [`client.py`](../../kwai_collector/client.py); rotas em
  [`scraper.py`](../../kwai_collector/scraper.py).
- **Exceções:** a troca de host móvel muda o gateway, não migra para a web.
- **Verificação:** `tests/test_cli.py`, `tests/test_client.py`.

## RN-002 — Limite da busca

- **Regra:** na CLI, o limite é inteiro ≥ 1, com padrão 20. Cada página pede
  `count=min(limit, 50)` e o `pcursor` avança de `count` em `count`; a palavra
  termina na primeira página sem post novo. O resultado final tem no máximo `limit` postagens
  únicas, e as palavras restantes não são consultadas depois que o limite é
  atingido. Palavras em branco são descartadas; sem nenhuma palavra válida, a
  entrada é rejeitada antes de qualquer requisição.
- **Motivação:** separar o tamanho da página pedida à API do teto total pedido
  pelo usuário.
- **Implementada em:** `search_posts` em `scraper.py`; opção `--limit` em
  [`cli.py`](../../kwai_collector/cli.py).
- **Exceções:** a API não devolve cursor nem lista vazia; quando a palavra se
  esgota, repete itens, por isso o fim é a página sem post novo. O `count` não
  diminui conforme o saldo entre palavras. A função Python não repete a validação `limit >= 1` da CLI.
- **Verificação:** `tests/test_cli.py` (`test_search`,
  `test_search_pagina_ate_nao_vir_post_novo`).

## RN-003 — Limite do perfil

- **Regra:** o limite do perfil conta postagens **únicas**. Sem limite, a coleta
  continua até o fim da paginação. Cada página pede 30 itens. Ao atingir o
  limite, a função devolve na hora, sem pedir outra página.
- **Motivação:** entregar exatamente a quantidade de posts distintos pedida.
- **Implementada em:** `get_user_posts` em `scraper.py`.
- **Exceções:** a CLI valida limite ≥ 1; a função Python trata `None` e `0`
  como “sem limite”.
- **Verificação:** `tests/test_cli.py` (`test_profile`).

## RN-004 — Limite de comentários

- **Regra:** o limite de `comments` conta comentários principais **únicos**.
  Respostas nunca consomem esse limite. Cada página de comentários principais
  pede 50 itens; ao atingir o limite, a função para sem pedir outra página.
- **Motivação:** deixar previsível quantos comentários principais vêm,
  independentemente de quantas respostas cada um tem.
- **Implementada em:** `get_root_comments` em `scraper.py`.
- **Exceções:** com `--with-replies`, o total de itens no arquivo pode ser muito
  maior que o limite (em uma verificação, `--limit 3` gerou 71 itens).
- **Verificação:** `tests/test_cli.py` (`test_comments_com_respostas`).

## RN-005 — Identidade e deduplicação

- **Regra:** postagens são identificadas pelo `id`. Comentários são
  identificados pelo `id`; sem `id`, pela string `"<id do autor>|<texto>"`. A
  primeira ocorrência é mantida e as seguintes são descartadas. Na expansão de
  respostas, um único conjunto guarda as chaves dos comentários principais e
  de todas as respostas já vistas.
- **Motivação:** páginas e palavras-chave podem se sobrepor; o JSON não deve
  repetir itens.
- **Implementada em:** `comment_key` e os conjuntos `seen` em `scraper.py`.
- **Exceções:** dois comentários sem id, do mesmo autor e com o mesmo texto são
  fundidos. Um `|` no texto pode, em tese, gerar colisão entre chaves sem id.
  Não há deduplicação entre execuções diferentes.
- **Verificação:** `tests/test_cli.py` (`test_comments_com_respostas`).

## RN-006 — Fim de paginação

- **Regra:** começar com cursor vazio. Depois de processar uma página, parar se
  ela veio vazia ou se o `pcursor` recebido for um sentinela de fim (`""`,
  `no_more`, `nomore`, `-1`, `0`). Um cursor que já apareceu nessa coleta
  também encerra a paginação, com warning.
- **Motivação:** obedecer à continuação devolvida pela API e não entrar em laço.
- **Implementada em:** `next_cursor` e os laços de `get_user_posts`,
  `get_root_comments` e `get_replies` em `scraper.py`.
- **Exceções:** no perfil, “página vazia” é a página **depois** da conversão:
  se todos os feeds de uma página forem ignorados pelo parser, a coleta para.
  Nos comentários e respostas, conta a lista crua. Cursor repetido não é erro:
  a coleta termina normalmente com o que já tem.
- **Verificação:** coberto indiretamente por `tests/test_cli.py`, que simula a
  página final com `pcursor: "no_more"`.

## RN-007 — Respostas são opcionais

- **Regra:** sem `--with-replies`, a saída é a lista de comentários principais
  (`Comment`). Com a opção, primeiro todos os comentários principais são
  coletados; depois, cada um vira `CommentWithReplies` com `respostas_total` e,
  se tiver `id` e total declarado diferente de zero e de `None`, suas respostas
  são buscadas (100 por página) e inseridas logo depois dele.
- **Motivação:** manter a saída simples igual ao schema `Comentario` e deixar
  explícito o custo extra das respostas.
- **Implementada em:** `get_comments` e `get_replies` em `scraper.py`.
- **Exceções:** a regra usa truthiness: um total negativo também dispara a
  busca de respostas.
- **Verificação:** `tests/test_cli.py` (`test_comments_com_respostas`).

## Relacionados

| Documento | Relação |
|---|---|
| [Busca](../flows/search.md) | RN-001, RN-002, RN-005. |
| [Perfil](../flows/profile.md) | RN-001, RN-003, RN-005, RN-006. |
| [Comentários](../flows/comments.md) | RN-001, RN-004 a RN-007. |
| [Paginação](../flows/pagination.md) | RN-006. |

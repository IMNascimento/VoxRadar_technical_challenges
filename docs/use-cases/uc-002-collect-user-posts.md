[⬅️ Casos de uso](./README.md) · [🏠 Índice](../README.md)

# 🎯 UC-002 — Coletar postagens de um perfil

| | |
|---|---|
| **Ator** | Usuário da CLI ou programa Python chamador. |
| **Objetivo** | Obter todas as postagens que a API móvel entrega para um perfil, paginadas e deduplicadas. |
| **Pré-condições** | Configuração válida, acesso HTTPS aos hosts móveis e usuário aceito pela validação local. |
| **Entrada** | `get_user_posts(user, limit=None)`; na CLI, `--user/-u` e `--limit/-l`. |
| **Implementação** | `get_user_posts` e `get_user_id` em [`scraper.py`](../../kwai_collector/scraper.py). |
| **Saída** | `list[Post]` na ordem do feed, sem repetidos. |

## Fluxo principal

1. Remover espaços e `@` do início e validar o usuário.
2. Gerar `coletado_em` e resolver o usuário no id numérico via `getInfo`.
3. Começar o feed com cursor vazio, pedindo 30 itens com a query mínima.
4. Converter os feeds em `Post` e acumular os de `id` ainda não visto.
5. Seguir o `pcursor` enquanto houver página, não houver fim e o limite não
   tiver sido atingido.
6. Devolver a lista; a CLI grava ou imprime o JSON.

## Fluxos alternativos

- **1a — Usuário inválido (vazio, com espaço, `/` ou `@`):** `InvalidInput`,
  exit `2`, sem requisição.
- **2a — Usuário não encontrado ou sem `user_id` numérico:** `KwaiError`, exit `1`.
- **3a — Hosts falham por falha passageira:** troca de host e novas rodadas
  conforme `max_retries`.
- **3b — Erro de negócio:** `KwaiError` sem troca de host nem retry.
- **4a — Página convertida vazia:** encerra; pode acontecer porque o parser
  ignorou todos os feeds da página, não necessariamente por falta de conteúdo.
- **5a — Limite atingido:** devolve na hora, sem pedir outra página.
- **5b — Cursor repetido:** warning e fim normal, com o que já foi coletado.
- **5c — Falha em página posterior:** descarta os posts já coletados; exit `1`.

## Pós-condições e limites

- Sem limite, o término segue o fim informado pela API, não uma prova de que
  todos os posts existentes foram coletados.
- Não há fallback para a web, para página HTML ou para navegador.
- O contexto completo também já entregou feeds no app; usar o mínimo não é uma
  proibição comprovada do completo.
- Sem checkpoint: outra execução resolve o usuário e pagina do início.
- Perfis grandes levam tempo: 7.389 posts levaram cerca de seis minutos com o
  intervalo padrão.

## Verificação

| Área | Testes |
|---|---|
| Resolução, corpo do feed, paginação e JSON | `tests/test_cli.py` (`test_profile`). |
| Assinatura e troca de host | `tests/test_client.py`. |
| Conversão de feed | `tests/test_parser.py`. |

## Relacionados

[Fluxo de perfil](../flows/profile.md) · [Paginação](../flows/pagination.md) ·
[RN-001, RN-003, RN-005 e RN-006](../business-rules/collection.md) ·
[RN-012 a RN-015](../business-rules/failure-policy.md) ·
[ADR-0001](../adr/0001-mobile-profile-and-comments.md) · [Assinatura](../internals/signature.md).

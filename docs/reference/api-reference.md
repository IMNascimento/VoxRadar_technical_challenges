[🏠 Índice](../README.md)

# Referência Python

## Status da interface

O projeto oferece uma CLI e funções Python utilizáveis a partir do checkout ou
de uma instalação local. Não há classe cliente, métodos assíncronos, API REST
própria nem promessa de estabilidade de SDK. Os imports começam com
`kwai_collector`.

Para uso normal, chame as três funções de
[`scraper.py`](../../kwai_collector/scraper.py). Só use `client.py` diretamente
quando precisar de uma requisição isolada ou estiver depurando o protocolo.

## Integração de alto nível

O exemplo abaixo faz rede quando executado. `@parkourcity` é um alvo
ilustrativo. As funções devolvem modelos Pydantic; a serialização e a
persistência ficam com o programa chamador.

```python
import json

from kwai_collector import scraper

posts = scraper.get_user_posts("@parkourcity", limit=2)
print(json.dumps([post.model_dump() for post in posts], ensure_ascii=False, indent=2))
```

Não há recurso para fechar: cada requisição usa `httpx.post`, que abre e fecha
a conexão na própria chamada. As funções são síncronas e sequenciais; não há
promessa de uso concorrente, porque o intervalo entre requisições é um estado
global do módulo `client`.

A biblioteca não configura logging. Num programa próprio, chame
`logging.basicConfig(level=logging.INFO)` se quiser ver os logs da coleta.

## Funções de coleta (`kwai_collector.scraper`)

| Função | Retorno | Levanta |
|---|---|---|
| `search_posts(keywords: list[str], limit: int = 20)` | `list[Post]` | `InvalidInput`, `KwaiError` |
| `get_user_posts(user: str, limit: int \| None = None)` | `list[Post]` | `InvalidInput`, `KwaiError` |
| `get_comments(post_url: str, limit: int \| None = None, with_replies: bool = False)` | `list[Comment]` | `InvalidInput`, `KwaiError` |

### `search_posts`

Remove espaços das bordas de cada palavra e descarta as que ficarem vazias. Sem
nenhuma palavra válida, levanta `InvalidInput`. Para cada palavra, pagina a
requisição web com `count=min(limit, 50)`, avançando o `pcursor` de `count` em
`count` até uma página sem post novo. Deduplica por `id` e para quando o total
atinge `limit`. Devolve no máximo `limit` posts.

A função não valida `limit >= 1`; essa validação é feita pela CLI.

### `get_user_posts`

Normaliza o usuário (remove espaços e `@` do início). Levanta `InvalidInput` se
o resultado ficar vazio ou contiver espaço, `/` ou `@`. Resolve o id numérico
com `get_user_id` e pagina o feed do perfil até o fim ou até `limit` posts
únicos. `limit=None` coleta tudo.

### `get_comments`

Extrai o id do post da URL com `get_photo_id`. Coleta os comentários principais
até o fim ou até `limit` comentários únicos. Com `with_replies=True`, devolve
uma lista plana de `CommentWithReplies`: cada comentário principal seguido das
suas respostas. O tipo declarado é `list[Comment]` porque `CommentWithReplies`
herda de `Comment`.

### Funções auxiliares

| Função | O que faz |
|---|---|
| `get_user_id(handle)` | Chama `getInfo` e devolve o `user_id` numérico como string. `KwaiError` se não encontrar. |
| `get_photo_id(url)` | Extrai o id de `/video/<id>` ou `/photo/<id>`. `InvalidInput` se não houver. |
| `get_root_comments(photo_id, post_url, collected_at, limit)` | Pagina os comentários principais. Devolve pares `(Comment, total de respostas declarado)`. |
| `get_replies(photo_id, post_url, root_id, collected_at)` | Pagina a sublista de respostas de um comentário. |
| `next_cursor(data, seen)` | Lê `pcursor` e decide se há próxima página. Veja [Paginação](../flows/pagination.md). |
| `comment_key(comment)` | Chave de deduplicação: `id` ou `"<id do autor>\|<texto>"`. |

Constantes: `SEARCH_PATH`, `USER_INFO_PATH`, `PROFILE_PATH`, `COMMENTS_PATH`,
`REPLIES_PATH`, `SEARCH_PAGE_SIZE` (50) e `END_CURSORS`.

## Exceções

| Exceção | Módulo | Quando |
|---|---|---|
| `InvalidInput` | `kwai_collector.scraper` | Entrada do usuário inválida. Levantada antes de qualquer requisição. A CLI converte em exit `2`. |
| `KwaiError` | `kwai_collector.client` | Falha de rede esgotada, status HTTP de erro, `result` diferente de 1 ou usuário não encontrado. A CLI converte em exit `1`. |
| `TransientError` | `kwai_collector.client` | Uso interno: marca uma falha passageira para o retry. Não sai de `post_web`/`post_mobile`. |
| `pydantic.ValidationError` | Pydantic | Configuração `KWAI_` inválida (na importação) ou dado que não cabe no modelo. Não é tratada pela CLI. |

`InvalidInput` e `KwaiError` herdam direto de `Exception`; não há hierarquia
comum. Não existe exceção de resultado parcial: quando uma coleta falha, os
itens já obtidos são descartados.

```python
from kwai_collector import scraper
from kwai_collector.client import KwaiError

try:
    comments = scraper.get_comments("https://www.kwai.com/@perfil/video/123", limit=10)
except scraper.InvalidInput as exc:
    print("entrada inválida:", exc)
except KwaiError as exc:
    print("falha na coleta:", exc)
```

## Cliente HTTP (`kwai_collector.client`)

| Símbolo | Papel |
|---|---|
| `post_web(path, payload)` | POST JSON em `https://www.kwai.com` com retry e checagem de `result`. Usado pela busca. |
| `post_mobile(path, query, body)` | Assina, envia formulário pelos hosts móveis em ordem, com retry e checagem de `result`. |
| `create_signature(params)` | Calcula o `sig`. Veja [Assinatura](../internals/signature.md). |
| `build_app_query()` | Cópia de `APP_QUERY` com `timestamp` e `session_id` novos. |
| `post_json(url, **kwargs)` | Uma tentativa: espera o intervalo, faz o POST e valida status e JSON. |
| `with_retry(func)` | Repete `func` em falha passageira, com backoff. |
| `check_result(data, path)` | Levanta `KwaiError` se `result` existir e for diferente de 1. |
| `wait_delay()` | Espera o intervalo mínimo desde a última requisição. |

Constantes: `WEB_URL`, `MOBILE_HOSTS`, `APP_VERSION`, `CLIENT_KEY`, `SIG_SALT`,
`APP_QUERY`, `WEB_HEADERS`, `APP_HEADERS` e `RETRY_STATUS`. Detalhes em
[Protocolo móvel](../internals/mobile-api.md).

Exemplo offline, sem rede:

```python
from kwai_collector.client import create_signature

print(create_signature({"count": "2", "kpn": "KWAI", "pcursor": "", "photoId": "123"}))
```

## Conversão (`kwai_collector.parser`)

| Função | Retorno |
|---|---|
| `parse_post(feed, collected_at)` | `Post`, ou `None` se o feed não tiver id ou usuário para montar a URL. |
| `parse_posts(feeds, collected_at)` | `list[Post]`; ignora itens que não são objetos e feeds sem URL montável. |
| `parse_comment(raw, post_url, collected_at)` | `Comment`. |
| `to_int(value)` | `int` ou `None`; rejeita `bool`. |
| `ms_to_iso(value)` | Timestamp em milissegundos para `AAAA-MM-DDTHH:MM:SSZ`, ou `None`. |
| `now_iso()` | Instante atual em UTC, no mesmo formato. |
| `clean_string(value)`, `clean_text(value)` | Texto sem espaços nas bordas; `clean_text` também decodifica entidades HTML. |
| `get_first_value(data, *keys)` | Primeiro valor não nulo entre as chaves. |

Mapeamento campo a campo em [Schemas](./schemas.md).

## Modelos (`kwai_collector.models`)

`Post`, `PostAuthor`, `Engagement`, `Comment`, `CommentAuthor` e
`CommentWithReplies`, todos `pydantic.BaseModel`. Use `model_dump()` para
obter o dicionário que a CLI grava. Veja [Schemas](./schemas.md).

## Configuração (`kwai_collector.config`)

| Símbolo | Interface |
|---|---|
| `Settings` | `BaseSettings` com `request_delay`, `http_timeout`, `max_retries`, `user_agent`. |
| `settings` | Instância única, criada na importação do módulo. |

`client.py` lê `settings` em cada requisição. Para mudar um valor em tempo de
execução (por exemplo, num teste), altere o atributo da instância:

```python
from kwai_collector.config import settings

settings.request_delay = 0
```

Os testes fazem isso com `monkeypatch` em [`tests/conftest.py`](../../tests/conftest.py).

## CLI (`kwai_collector.cli`)

`app` é a aplicação Typer usada pelo script `kwai-collector` e por
`python -m kwai_collector`. `collect_and_save(collect, out)` executa a coleta,
converte exceções em códigos de saída e grava ou imprime o JSON. Veja
[CLI](../guides/cli.md).

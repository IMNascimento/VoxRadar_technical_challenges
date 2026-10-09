[🏠 Índice](../README.md)

# Referência Python

## Status da interface

O projeto oferece uma CLI e componentes Python utilizáveis a partir do checkout
ou instalação local. Não há facade `KwaiClient`, métodos assíncronos, API REST
própria, promessa de estabilidade de SDK ou pacote publicado assumido por esta
documentação. Os imports efetivos são `src.*`.

Para uso normal, prefira [`build_services`](../../src/container.py). Só construa
adapters diretamente quando precisar controlar uma página ou testar uma porta.
Métodos iniciados por `_` são detalhes de implementação, não extensões públicas.

## Integração de alto nível

O exemplo abaixo faz rede quando executado. `@parkourcity` é um alvo ilustrativo.
Ele devolve modelos; a serialização e a persistência ficam com o programa chamador.

```python
from src.config import Settings
from src.container import build_services

settings = Settings()
with build_services(settings) as services:
    posts = services.user_posts.execute("@parkourcity", limit=2)

payload = [post.model_dump() for post in posts]
print(payload)
```

`Services` fecha os dois clientes ao sair do `with`, mesmo quando a coleta lança
uma exceção. `close()` registra callbacks em `ExitStack`: ambos são tentados se
um fechamento falhar. Isso não significa que erros de fechamento sejam engolidos.
Exceções de fechamento podem afetar a exceção que chega ao chamador; examine a
cadeia se estiver investigando um problema de lifecycle.

Os casos de uso isolados não possuem `close()`: eles não são donos dos adapters.
Não há promessa de uso concorrente do conjunto inteiro de serviços; cada
coleta documentada é síncrona e sequencial.

### `Settings` e `Services`

| Símbolo | Módulo | Interface |
|---|---|---|
| `Settings` | `src.config` | Campos `request_delay`, `http_timeout`, `max_retries`, `user_agent`. |
| `build_services(settings)` | `src.container` | Retorna `Services`, criando um adapter web e um móvel. |
| `Services.search_posts` | `src.container` | Instância de `SearchPosts`. |
| `Services.user_posts` | `src.container` | Instância de `CollectUserPosts`. |
| `Services.comments` | `src.container` | Instância de `CollectComments`. |
| `Services.comment_versions` | `src.container` | Instância de `CollectCommentVersions`. |
| `Services.profile_bundle` | `src.container` | Instância de `CollectProfileBundle`. |
| `Services.close()` | `src.container` | Encerra os recursos HTTP. Preferir o context manager. |

Configurações explícitas são úteis para testes, por exemplo
`Settings(request_delay=0, max_retries=0)`. Não use ausência de espera como
recomendação de coleta em volume; veja [Primeiros passos](../guides/getting-started.md).

## Casos de uso

| Classe | Construtor | Método | Retorno |
|---|---|---|---|
| `SearchPosts` | `SearchPosts(api: SearchApiPort)` | `execute(keywords: list[str], *, limit: int = 20, sort_by: str \| None = None)` | `list[Post]`. |
| `CollectUserPosts` | `CollectUserPosts(api: ProfileApiPort)` | `execute(user: str, *, limit: int \| None = None, sort_by: str \| None = None)` | `list[Post]`. |
| `CollectComments` | `CollectComments(api: CommentApiPort)` | `execute(post_url: str, *, limit: int \| None = None, with_replies: bool = False)` | `list[Comment]`; com respostas, itens `ExpandedComment`. |

`SearchPosts` rejeita lista de palavras vazia. `CollectUserPosts` normaliza o
handle antes de resolver seu id. `CollectComments` extrai o id de `/video/` ou
`/photo/` da string recebida. Esse extrator não valida host completo: não use
seu sucesso como certificação de origem de uma URL.

As validações `min=1` dos limites são da CLI. A API Python dos casos de uso não
repete essa validação; passe `limit` positivo ou `None` onde permitido. Não há
contrato útil documentado aqui para limites negativos/zero fora da CLI.

Limites, deduplicação, páginas vazias e ciclos de cursor estão em
[Fluxos](../flows/README.md). Retornos são listas materializadas; não há streaming público
de itens nesses métodos.

`sort_by` aceita `likes`, `comments`, `shares` ou `views` e rejeita outros valores
com `InvalidInputError` antes de fazer rede. Ordena o conjunto obtido após o limite,
sempre do maior para o menor; não filtra itens nem combina métricas. `None`
preserva a ordem original. Empates são estáveis; contagens desconhecidas ficam
no fim. Se a coleta falhar, o parcial de posts segue a mesma ordenação, preservando
a causa. Os modelos e métricas não são modificados.

### Coleta combinada

`CollectCommentVersions.execute(post_url, *, limit=None, with_comments=True,
with_replies=False)` e `CollectProfileBundle.execute(user, options)` entregam
iteradores de `CollectionResult`, não itens individuais. `ProfileCollectionOptions`
fica em `application/collect_profile_bundle.py`, com `limit`, `comments_limit`,
`with_comments`, `with_replies` e `sort_by`. Esses novos fluxos validam limites positivos.

`CollectionResult` contém `kind`, `items`, `stage`, `post_url` e `error`.
`stage` é atribuído no ponto da coleta (`posts`, `roots`, `replies`), nunca
deduzido de `parent_id` ou do tipo do parcial. Raízes são coletadas uma vez;
duas versões podem ser entregues separadamente. Falhas operacionais aparecem
no resultado; entrada inválida continua sendo erro. O consumidor deve verificar
`error` ao consumir **todos** os resultados, sem interpretar o iterador como
garantia de sucesso. A CLI grava as unidades antes de fechar os serviços.

## Exceções e resultado parcial

| Exceção | Import | Situação |
|---|---|---|
| `KwaiCollectorError` | `src.domain.exceptions` | Base dos erros esperados da coleta. |
| `InvalidInputError` | Mesmo módulo | Handle, id/URL ou entrada reconhecida como inválida. |
| `KwaiApiError` | Mesmo módulo | Erro de negócio; atributo `result` guarda o código recebido. |
| `KwaiTransportError` | `src.infrastructure.exceptions` | Transporte/status sem recuperação disponível. |
| `UnexpectedResponseError` | Mesmo módulo | JSON ou estrutura da resposta não aceitos. |
| `RepeatedCursorError` | `src.application.exceptions` | Continuação já vista. |
| `CollectionInterruptedError` | Mesmo módulo | Falha após obter itens; `partial` e `__cause__` preservam contexto. |

Capture `CollectionInterruptedError` **antes** de `KwaiCollectorError`, pois a
primeira herda da segunda. `partial` é uma tupla de `BaseModel`, não uma tupla
estaticamente especializada para cada comando. Não suponha um tipo de item
sem verificar ou serializar pelo contrato comum.

Este exemplo também faz rede. Mostra explicitamente como diferenciar parcial
de sucesso; não transforma a falha em resultado completo:

```python
from src.application.exceptions import CollectionInterruptedError
from src.config import Settings
from src.container import build_services
from src.domain.exceptions import KwaiCollectorError

try:
    with build_services(Settings()) as services:
        posts = services.user_posts.execute("@parkourcity", limit=2)
except CollectionInterruptedError as error:
    payload = [item.model_dump() for item in error.partial]
    print({"complete": False, "items": payload, "error": str(error.__cause__)})
except KwaiCollectorError:
    raise
else:
    print({"complete": True, "items": [post.model_dump() for post in posts]})
```

`complete` acima é um sinal **do chamador** sobre conclusão sem interrupção;
não pertence ao JSON do coletor e não prova completude na plataforma. A CLI não
inclui esse envelope: grava apenas a lista e sinaliza falha com exit `1`.

Erros de validação Pydantic, I/O do chamador e exceções inesperadas não são todos
convertidos em `KwaiCollectorError`. Defina sua política de fronteira separadamente.

## Adapters e portas de uma página

| Adapter | Porta implementada | Uso |
|---|---|---|
| `KwaiWebAdapter(settings)` | `SearchApiPort` | Um lote por palavra-chave. |
| `MobileApiAdapter(settings)` | `ProfileApiPort`, `CommentApiPort` | Resolução de usuário e páginas móveis. |

Ambos expõem `close()` e não implementam context manager próprio. Se instanciados
diretamente, use `try/finally` para fechar. `Services` é o context manager disponível.

As assinaturas abaixo são **referência de interface**, não código para executar:

```text
SearchApiPort.search_posts(keyword: str, count: int, *, collected_at: IsoTimestamp)
    -> list[Post]
ProfileApiPort.resolve_user(handle: Handle) -> UserId
ProfileApiPort.fetch_profile_page(user_id: UserId, *, cursor: Cursor,
    count: int, collected_at: IsoTimestamp) -> ProfilePage
CommentApiPort.fetch_page(photo_id: PhotoId, *, cursor: Cursor, count: int,
    postagem_url: str, collected_at: IsoTimestamp) -> CommentPage
CommentApiPort.fetch_sub_page(photo_id: PhotoId, *, root_comment_id: CommentId,
    cursor: Cursor, count: int, postagem_url: str,
    collected_at: IsoTimestamp) -> SubCommentPage
```

Uma chamada de página não percorre a lista toda. A aplicação decide continuar.
Os `Protocol` são seams de I/O para substituir uma porta por fake sem fazer HTTP;
não são um sistema de plugins registrável em runtime.

### Objetos de página

Todos vivem em [`src.application.ports`](../../src/application/ports.py) como
dataclasses `frozen=True`; as listas internas não viram coleções profundamente imutáveis.

| Objeto | Campos |
|---|---|
| `ProfilePage` | `posts: list[Post]`, `next_cursor: Cursor`. |
| `CommentPage` | `comments: list[RootComment]`, `next_cursor: Cursor`. |
| `RootComment` | `comentario: Comment`, `respostas_declaradas: int \| None`. |
| `SubCommentPage` | `comments: list[SubComment]`, `next_cursor: Cursor`. |
| `SubComment` | `comentario: Comment`, `reply_to_id`, `reply_to_usuario`. |

### Value objects

| Tipo | Regra relevante |
|---|---|
| `Handle` | Não vazio, sem `@`, espaço ou `/`, sem espaço de borda. Normalizar via `normalize_handle` quando a entrada for do usuário. |
| `PhotoId` / `UserId` | String para a qual `isdigit()` é verdadeiro; não são inteiros de máquina. |
| `CommentId` | Não vazio, sem espaço de borda; não exige formato numérico. |
| `Cursor` | Encapsula string e reconhece sentinelas de fim. Não calcula a próxima página. |
| `IsoTimestamp` | String que casa com o padrão `YYYY-MM-DDTHH:MM:SSZ`; valida a forma por regex, não a existência da data no calendário. |

Tipos vivem em [`domain/value_objects`](../../src/domain/value_objects).
As validações de `isdigit()` não equivalem a uma restrição ASCII de ids.

## Helpers documentados para manutenção

| Símbolo | Papel |
|---|---|
| `compute_sig(params: Mapping[str, str]) -> str` | Fórmula em [Assinatura](../internals/signature.md). |
| `parse_feed`, `parse_comment`, `parse_sub_comment` | Mapeamento em [Schemas](./schemas.md). |
| `iter_pages(fetch, *, is_empty, source)` | Gerador preguiçoso de páginas; não persiste cursor. |

Para integração mantenha dependência nos casos de uso; helpers e adapters estão
expostos pelo código, mas acoplam o chamador a detalhes de manutenção do protocolo.

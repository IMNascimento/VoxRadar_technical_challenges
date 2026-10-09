[🏠 Índice](../README.md)

# Referência Python

## Status da interface

O projeto oferece uma CLI e componentes Python utilizáveis a partir do checkout
ou instalação local. Não há facade `KwaiClient`, métodos assíncronos, API REST
própria, promessa de estabilidade de SDK ou pacote publicado assumido por esta
documentação. Os imports efetivos são `src.*`.

Para uso normal, prefira [`build_services`](../../src/infrastructure/container/container.py). Só construa
adapters diretamente quando precisar controlar uma página ou testar uma porta.
Métodos iniciados por `_` são detalhes de implementação, não extensões públicas.

## Integração de alto nível

O exemplo abaixo faz rede quando executado. `@parkourcity` é um alvo ilustrativo.
Ele devolve entidades (dataclasses imutáveis do domínio); a serialização e a
persistência ficam com o programa chamador.

```python
from dataclasses import asdict

from src.application.dtos.commands import ProfileCollectionCommand
from src.config.settings import Settings
from src.infrastructure.container.container import build_services

command = ProfileCollectionCommand.create("@parkourcity", limit=2)
with build_services(Settings()) as services:
    (posts,) = services.profile_bundle.execute(command)

print([asdict(post) for post in posts.items])
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
| `Settings` | `src.config.settings` | Campos `request_delay`, `http_timeout`, `max_retries`, `user_agent`. |
| `build_services(settings)` | `src.infrastructure.container.container` | Retorna `Services`, criando os clientes e adapters web e móvel e o relógio. |
| `Services.search_posts` | `src.infrastructure.container.container` | Porta `ISearchPostsPort`, implementada por `SearchPosts`. |
| `Services.comment_versions` | `src.infrastructure.container.container` | Porta `ICollectCommentVersionsPort`, implementada por `CollectCommentVersions`. |
| `Services.profile_bundle` | `src.infrastructure.container.container` | Porta `ICollectProfileBundlePort`, implementada por `CollectProfileBundle`. |
| `Services.close()` | `src.infrastructure.container.container` | Encerra os recursos HTTP. Preferir o context manager. |

Configurações explícitas são úteis para testes, por exemplo
`Settings(request_delay=0, max_retries=0)`. Não use ausência de espera como
recomendação de coleta em volume; veja [Primeiros passos](../guides/getting-started.md).

## Casos de uso

| Classe | Construtor | Método | Retorno |
|---|---|---|---|
| `SearchPosts` | `SearchPosts(api: ISearchApiPort, clock: IClockPort)` | `execute(command: SearchCommand)` | `CollectionResult[Post]`. |
| `CollectCommentVersions` | `CollectCommentVersions(api: ICommentApiPort, clock: IClockPort)` | `execute(command: CommentCollectionCommand)` | `Iterator[CollectionResult[Comment]]`. |
| `CollectProfileBundle` | `CollectProfileBundle(posts: ICollectUserPostsPort, comments: ICollectCommentVersionsPort)` | `execute(command: ProfileCollectionCommand)` | `Iterator[CollectionResult[Post \| Comment]]`. |

As portas de entrada vivem em `src.application.ports.use_case_ports`:
`ISearchPostsPort`, `ICollectUserPostsPort`, `ICollectCommentVersionsPort` e
`ICollectProfileBundlePort`. Cada uma declara somente `execute`, com o mesmo
comando e retorno do caso de uso correspondente. O container escolhe as
implementações; a CLI e o bundle consomem os contratos.

`CollectUserPosts(api: IProfileApiPort, clock).execute(command: ProfileCollectionCommand)`
devolve `list[Post]` e é injetado em `CollectProfileBundle`; falhas sobem como
exceção (veja abaixo). O bundle referencia cada postagem pelo `id` coletado
(`reference_post`); postagem sem id numérico vira resultado `comments` com
`InvalidValueError`, e as demais seguem. `IClockPort` (método `now() -> IsoTimestamp`) fica em
`src.application.ports.clock_port`; o container injeta `SystemClock`, e testes
injetam um relógio fixo. Cada execução lê o relógio uma única vez.

### Comandos de entrada

Os comandos vivem em [`src.application.dtos.commands`](../../src/application/dtos/commands.py)
e validam a entrada **ao serem criados**, antes de qualquer requisição. O caso de
uso recebe os valores já validados e não repete a validação.

| Comando | Fábrica | Campos validados |
|---|---|---|
| `SearchCommand` | `create(keywords, *, limit=20, sort_by=None)` | `keywords` não vazio e nenhuma palavra-chave em branco; `limit` positivo; `sort_by` → `PostSortBy`. |
| `CommentCollectionCommand` | `create(post_url, *, limit=None, versions=CommentVersions.ROOTS)` | URL → `PostReference` (id de `/video/` ou `/photo/`); `limit` positivo. |
| `ProfileCollectionCommand` | `create(user, *, limit=None, comments_limit=None, comment_versions=None, sort_by=None)` | Conta → `Handle` normalizado; limites positivos; `sort_by` → `PostSortBy`. `comment_versions=None` dispensa comentários. |

`CommentVersions` (mesmo módulo) escolhe as versões de comentários: `ROOTS`,
`REPLIES` ou `ALL`; `has_roots`/`has_replies` dizem o que é entregue. Pedir
comentários sem nenhuma versão não é representável.
`CommentVersions.from_flags(roots=..., replies=...)` converte as opções da CLI e
devolve `None` quando nenhuma foi pedida.

Entrada inválida lança `InvalidInputError` na criação do comando. O extrator de
id da URL não valida host completo: não use seu sucesso como certificação de
origem de uma URL. A CLI também valida limites com `min=1`.

Limites, deduplicação, páginas vazias e ciclos de cursor estão em
[Fluxos](../flows/README.md). Os itens de cada resultado são tuplas materializadas;
não há streaming público de itens individuais.

`sort_by` aceita `likes`, `comments`, `shares` ou `views` e rejeita outros valores
com `InvalidInputError` antes de fazer rede. Ordena o conjunto obtido após o limite,
sempre do maior para o menor; não filtra itens nem combina métricas. `None`
preserva a ordem original. Empates são estáveis; contagens desconhecidas ficam
no fim. Se a coleta falhar, o parcial de posts segue a mesma ordenação, preservando
a causa. Os modelos e métricas não são modificados.

### Resultados

`CollectionResult[T]` contém `kind`, `items: tuple[T, ...]`, `post` e `error`.
`post` é um `PostReference` (`photo_id`, `url` e `owner`) e é obrigatório quando `kind`
não é `posts`, exceto em resultado de falha cuja postagem não pôde ser
identificada (senão, `ValueError`). `CollectionResult.failed(kind, exc, item_type)`
monta o resultado de falha com o parcial tipado. `stage` é derivado de `kind` (`posts`→`posts`, `comments`→`roots`,
`comments-replies`→`replies`), nunca de `parent_id` ou do tipo do parcial. Raízes são coletadas uma vez;
duas versões podem ser entregues separadamente. Falhas operacionais aparecem
no resultado; entrada inválida continua sendo erro. O consumidor deve verificar
`error` ao consumir **todos** os resultados, sem interpretar o iterador como
garantia de sucesso. A CLI grava as unidades antes de fechar os serviços.

## Exceções e resultado parcial

| Exceção | Import | Situação |
|---|---|---|
| `KwaiCollectorError` | `src.domain.exceptions.domain_exceptions` | Base dos erros esperados da coleta. |
| `InvalidInputError` | Mesmo módulo | Handle, id/URL, limite ou entrada reconhecida como inválida. |
| `InvalidValueError` | Mesmo módulo | Id de postagem/comentário/usuário ou timestamp vindo da API fora da invariante do value object. |
| `RepeatedCursorError` | Mesmo módulo | Continuação já vista (regra de paginação do domínio). |
| `ExternalServiceError` | `src.application.exceptions` | Base das falhas do serviço externo atrás das portas; separa essas falhas dos erros de entrada/valor. |
| `KwaiTransportError` | `src.infrastructure.kwai.exceptions` | Transporte/status sem recuperação disponível. |
| `UnexpectedResponseError` | Mesmo módulo | JSON ou estrutura da resposta não aceitos. |
| `KwaiApiError` | Mesmo módulo | Erro de negócio do protocolo (campo `result`); atributo `result` guarda o código recebido. |
| `CollectionInterruptedError` | `src.application.exceptions` | Falha após obter itens; `partial` e `__cause__` preservam contexto. |

Os casos de uso expostos por `Services` não lançam falhas de coleta: elas
aparecem em `CollectionResult.error`, com o parcial em `items`. Quando a falha
interrompe uma coleta que já tinha itens, `error` é um `CollectionInterruptedError`
cuja causa original fica em `__cause__`. `CollectUserPosts`, usado diretamente,
lança essas exceções; capture `CollectionInterruptedError` **antes** de
`KwaiCollectorError`, pois a primeira herda da segunda. `KwaiTransportError`,
`UnexpectedResponseError` e `KwaiApiError` herdam de `ExternalServiceError`, que
herda de `KwaiCollectorError`: capture a família externa quando quiser reagir
só a ela. `CollectionInterruptedError` é genérica no tipo do `partial`, mas o
tipo se perde ao capturar; `partial_items(exc, Post)`, de
`src.application.exceptions`, devolve os itens tipados (vazio para falhas sem parcial).

Este exemplo também faz rede. Mostra explicitamente como diferenciar parcial
de sucesso; não transforma a falha em resultado completo:

```python
from dataclasses import asdict

from src.application.dtos.commands import SearchCommand
from src.config.settings import Settings
from src.infrastructure.container.container import build_services

with build_services(Settings()) as services:
    result = services.search_posts.execute(SearchCommand.create(["sports"], limit=2))

payload = [asdict(post) for post in result.items]
print({"complete": result.error is None, "items": payload, "error": str(result.error)})
```

`complete` acima é um sinal **do chamador** sobre conclusão sem interrupção;
não pertence ao JSON do coletor e não prova completude na plataforma. A CLI não
inclui esse envelope: grava apenas a lista e sinaliza falha com exit `1`.

Erros de I/O do chamador e exceções inesperadas não são todos convertidos em
`KwaiCollectorError`. Defina sua política de fronteira separadamente.

## Adapters e portas de uma página

| Cliente | Adapter | Porta implementada | Uso |
|---|---|---|---|
| `KwaiWebClient(settings)` (`src.infrastructure.kwai.web.client`) | `KwaiWebAdapter(client)` (`...web.adapter`) | `ISearchApiPort` | Um lote por palavra-chave. |
| `MobileApiClient(settings)` (`src.infrastructure.kwai.mobile.client`) | `MobileApiAdapter(client)` (`...mobile.adapter`) | `IProfileApiPort`, `ICommentApiPort` | Resolução de usuário e páginas móveis. |

O cliente é dono da sessão HTTP, do rate limit, do retry e (no móvel) da
assinatura e da escada de gateways; o adapter conhece rota, contexto, corpo,
tamanho de página e mapeamento. Só os clientes expõem `close()` e não implementam
context manager próprio. Se instanciados diretamente, use `try/finally` para
fechá-los. `Services` é o context manager disponível.

As assinaturas abaixo são **referência de interface**, não código para executar:

```text
ISearchApiPort.search_posts(keyword: str, *, limit: int, collected_at: IsoTimestamp)
    -> list[Post]
IProfileApiPort.resolve_user(handle: Handle) -> UserId
IProfileApiPort.fetch_profile_page(user_id: UserId, *, cursor: Cursor,
    collected_at: IsoTimestamp) -> ProfilePage
ICommentApiPort.fetch_page(post: PostReference, *, cursor: Cursor,
    collected_at: IsoTimestamp) -> CommentPage
ICommentApiPort.fetch_sub_page(post: PostReference, *, root_comment_id: CommentId,
    cursor: Cursor, collected_at: IsoTimestamp) -> SubCommentPage
```

Uma chamada de página não percorre a lista toda. A aplicação decide continuar.
O tamanho de página é decisão do adapter, que conhece o endpoint
(`COMMENTS_PAGE_SIZE`, `SUBLIST_PAGE_SIZE` e `PROFILE_PAGE_SIZE` no adapter móvel;
`SEARCH_MAX_COUNT` no web, que limita o lote pedido por palavra-chave).
As portas são classes abstratas (`ABC`) que servem de seam de I/O: um fake que herda a porta a substitui sem fazer HTTP;
não são um sistema de plugins registrável em runtime.

### Objetos de página

Todos vivem em [`src.application.dtos.pages`](../../src/application/dtos/pages.py) como
dataclasses `frozen=True`; as listas internas não viram coleções profundamente imutáveis.

| Objeto | Campos |
|---|---|
| `ProfilePage` | `posts: list[Post]`, `next_cursor: Cursor`. |
| `CommentPage` | `comments: list[RootComment]`, `next_cursor: Cursor`. |
| `RootComment` | `comment: Comment`, `declared_replies: int \| None`. |
| `SubCommentPage` | `comments: list[SubComment]`, `next_cursor: Cursor`. |
| `SubComment` | `comment: Comment`, `reply_to_id`, `reply_to_usuario`. |

### Value objects

| Tipo | Regra relevante |
|---|---|
| `Handle` | Não vazio, sem `@`, `/` ou whitespace (inclusive tabs, quebras de linha e espaços Unicode). Normalizar via `Handle.parse` quando a entrada for do usuário. |
| `PhotoId` / `UserId` | String para a qual `isdigit()` é verdadeiro; não são inteiros de máquina. |
| `CommentId` | Não vazio, sem espaço de borda; não exige formato numérico. |
| `Cursor` | Encapsula string; vazio marca o fim. Os sentinelas do Kwai são traduzidos pelo adapter. Não calcula a próxima página. |
| `IsoTimestamp` | String no padrão `YYYY-MM-DDTHH:MM:SSZ`, com data e horário válidos. `from_datetime` exige fuso definido e converte o instante para UTC nesse formato. Valores inválidos geram `InvalidValueError`. |
| `PostReference` | `photo_id: PhotoId`, `url` e `owner` (handle do segmento `@perfil`, quando houver); construída por `parse_post_reference` (`domain/services/post_urls.py`), que extrai o id de `/video/` ou `/photo/`. |

Tipos vivem em [`domain/value_objects`](../../src/domain/value_objects).
As validações de `isdigit()` não equivalem a uma restrição ASCII de ids.

## Helpers documentados para manutenção

| Símbolo | Papel |
|---|---|
| `compute_sig(params: Mapping[str, str]) -> str` | Fórmula em [Assinatura](../internals/signature.md). |
| `parse_feed`, `parse_comment`, `parse_sub_comment` | Mapeamento em [Schemas](./schemas.md). |
| `iter_pages(fetch, *, is_empty, source)` | Coordenação na aplicação (`src.application.pagination`): gerador preguiçoso de páginas; não persiste cursor. |
| `get_continuation_cursor(cursor, *, is_empty, seen_cursors, source)` | Serviço puro de domínio (`src.domain.services.pagination`): retorna a continuação, `None` no fim ou levanta `RepeatedCursorError`; não busca páginas nem altera os cursores recebidos. |
| `unique_posts()`, `unique_comments()` | Serviço de domínio (`src.domain.services.identity`): `UniqueItems` que mantém a primeira ocorrência por `dedup_key` da entidade; uma instância compartilhada deduplica entre lotes. |
| `Post.dedup_key`, `Comment.dedup_key`, `Engagement.count(metric)` | Comportamento das entidades: identidade na deduplicação e contagem usada na ordenação. Propriedades e métodos não entram no JSON (`asdict`). |
| `declares_replies`, `replies_diverge` | Serviço de domínio (`src.domain.services.replies`): elegibilidade da raiz para expansão e divergência entre total declarado e entregue. |
| `post_url`, `profile_url`, `parse_post_reference`, `reference_post` | Serviço de domínio (`src.domain.services.post_urls`): única fonte do formato das URLs públicas do Kwai. |

Para integração mantenha dependência nos casos de uso; helpers e adapters estão
expostos pelo código, mas acoplam o chamador a detalhes de manutenção do protocolo.

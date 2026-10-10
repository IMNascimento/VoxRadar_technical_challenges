[🏠 Índice](../README.md)

# Schemas e mapeamento

Este é o contrato **implementado** em
[`kwai_collector/models.py`](../../kwai_collector/models.py). Ele segue os
schemas `Postagem` e `Comentario` do desafio: mesmos nomes de campo, em
português, e os mesmos campos obrigatórios.

## Modelos de saída

Todos os modelos são `pydantic.BaseModel`. O construtor valida tipos, exige os
campos obrigatórios e aplica o formato de data nos campos marcados. Campos
extras são **ignorados** (comportamento padrão do Pydantic), não rejeitados.

As datas seguem o padrão `ISO_DATE`:

```text
^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$
```

Ou seja, UTC com precisão de segundos e sufixo `Z`, como `2026-07-27T14:30:00Z`.

### `Post` (schema `Postagem`)

| Campo | Tipo Python | Obrigatório | Observação |
|---|---|---|---|
| `id` | `str \| None` | Não | Id da postagem. |
| `url` | `str` | Sim | URL montada pelo parser. |
| `autor` | `PostAuthor` | Sim | Campos internos opcionais. |
| `texto` | `str \| None` | Não | Legenda limpa, com entidades HTML decodificadas. |
| `data_publicacao` | `str \| None` | Não | Validada por `ISO_DATE` quando presente. |
| `engajamento` | `Engagement` | Sim | Métricas opcionais. |
| `coletado_em` | `str` | Sim | Validada por `ISO_DATE`. |

`PostAuthor` contém `usuario`, `id` e `url_perfil`, todos `str | None`.
`Engagement` contém `curtidas`, `comentarios`, `compartilhamentos` e
`visualizacoes`, todos `int | None`. O modelo não impõe mínimo zero.

### `Comment` (schema `Comentario`)

| Campo | Tipo Python | Obrigatório | Observação |
|---|---|---|---|
| `id` | `str \| None` | Não | Id do comentário. |
| `postagem_url` | `str` | Sim | URL informada pelo usuário, sem alteração. |
| `autor` | `CommentAuthor` | Sim | `usuario` e `id`, ambos opcionais. |
| `texto` | `str` | Sim | String vazia se o conteúdo vier ausente ou vazio. |
| `curtidas` | `int \| None` | Não | Curtidas do comentário. |
| `data` | `str \| None` | Não | Validada por `ISO_DATE` quando presente. |
| `coletado_em` | `str` | Sim | Validada por `ISO_DATE`. |

### `CommentWithReplies`

Herda `Comment` e acrescenta quatro campos com padrão `None`. É usado só com
`--with-replies`. O schema do desafio aceita campos extras, desde que os
obrigatórios existam.

| Campo | Tipo | Comentário principal | Resposta |
|---|---|---|---|
| `parent_id` | `str \| None` | `null` | Id do comentário principal. |
| `reply_to_id` | `str \| None` | `null` | Id do **usuário** respondido, não id de comentário. |
| `reply_to_usuario` | `str \| None` | `null` | Nome do usuário respondido. |
| `respostas_total` | `int \| None` | Total de respostas informado pela API. | `null`. |

A lista é plana: comentário principal, suas respostas, próximo comentário
principal. Os campos extras aparecem como `null` quando não se aplicam.
`respostas_total` não é recalculado para bater com a quantidade entregue e não
significa completude.

## Exemplo sintético offline

```python
from kwai_collector.models import Engagement, Post, PostAuthor

post = Post(
    id="123",
    url="https://www.kwai.com/@perfil/video/123",
    autor=PostAuthor(usuario="@perfil"),
    engajamento=Engagement(curtidas=0),
    coletado_em="2026-10-09T00:00:00Z",
)
assert post.engajamento.curtidas == 0
assert post.engajamento.comentarios is None
print(post.model_dump())
```

JSON ilustrativo de um comentário principal e uma resposta (não é captura real):

```json
[
  {
    "id": "r1", "postagem_url": "https://www.kwai.com/@perfil/video/123",
    "autor": {"usuario": "Autor", "id": "u1"}, "texto": "Comentário",
    "curtidas": 0, "data": null, "coletado_em": "2026-10-09T00:00:00Z",
    "parent_id": null, "reply_to_id": null, "reply_to_usuario": null,
    "respostas_total": 2
  },
  {
    "id": "s1", "postagem_url": "https://www.kwai.com/@perfil/video/123",
    "autor": {"usuario": "Outro autor", "id": "u2"}, "texto": "Resposta",
    "curtidas": null, "data": null, "coletado_em": "2026-10-09T00:00:00Z",
    "parent_id": "r1", "reply_to_id": "u1", "reply_to_usuario": "Autor",
    "respostas_total": null
  }
]
```

## Campos externos → modelo

O mapeamento fica em [`kwai_collector/parser.py`](../../kwai_collector/parser.py).

### Feed → `Post`

O mesmo formato de feed vem da busca web e do feed de perfil móvel.

| Destino | Fonte e regra atual |
|---|---|
| `id` | Primeiro não nulo entre `photo_id_str` e `photo_id`; convertido para string e sem espaços nas bordas. |
| `url` | `https://www.kwai.com/@{handle}/video/{id}`; o handle é o primeiro não nulo entre `kwai_id` e `user_id_str`. |
| `autor.usuario` | `@` + `kwai_id`, se `kwai_id` for truthy; senão `user_name`. |
| `autor.id` | Primeiro não nulo entre `user_id_str` e `user_id`. |
| `autor.url_perfil` | `https://www.kwai.com/@{handle}`. |
| `texto` | Primeiro não nulo entre `caption` e `user_text`; sem espaços nas bordas e com `html.unescape`. |
| `data_publicacao` | `timestamp`, convertido de milissegundos. |
| `engajamento.curtidas` | `like_count`. |
| `engajamento.comentarios` | `comment_count`. |
| `engajamento.compartilhamentos` | `forward_count`. |
| `engajamento.visualizacoes` | `view_count`. |

Um feed sem id ou sem handle não permite montar a URL: é ignorado com o warning
`post ignorado: veio sem photo_id ou usuário`, e os demais continuam.
“Primeiro não nulo” não significa “primeiro não vazio”: se `photo_id_str` vier
como string vazia, o parser não volta para `photo_id` depois de limpar.

### Comentário e resposta → `Comment`

| Destino | Fonte e regra atual |
|---|---|
| `id` | Primeiro não nulo entre `comment_id` e `id`. |
| `postagem_url` | URL passada pelo usuário em `--url`. |
| `autor.usuario`, `autor.id` | `author_name`, `author_id`. |
| `texto` | `content`, limpo e com entidades HTML decodificadas; `""` se vazio. |
| `curtidas` | `liked_count`. |
| `data` | `timestamp`, convertido de milissegundos. |
| `respostas_total` | `sub_comment_count` do comentário principal, convertido para inteiro. |
| `reply_to_id` | `reply_to` da resposta; `"0"` vira `None`. |
| `reply_to_usuario` | `replyToUserName` da resposta. |
| `parent_id` | Adicionado pelo coletor com o id do comentário principal. |

Prévias de respostas embutidas na lista de comentários (`subCommentsMap`) não
são usadas. As respostas vêm sempre da rota `sublist`.

## Conversão e tolerância

| Dado | Política implementada |
|---|---|
| Métrica ausente | `None` → `null`; nunca vira zero. Zero só aparece quando a API mandou zero. |
| Escalar numérico | `int()` para int, float ou string; booleanos viram `None`. `3.9` vira `3`; a string `"3.9"` vira `None`. |
| Valor não conversível ou estrutura | `None`. |
| Timestamp | Ausente, zero, negativo ou inválido vira `None`; válido vira UTC com `Z`. |
| `feeds` ausente ou nulo | Lista vazia. |
| Item de feed que não é objeto | Ignorado sem warning. |
| Feed sem URL montável | Ignorado com warning. |

A estrutura de `rootComments`, `subComments` e `users` não é validada antes do
uso. Se a API mudar o formato dessas listas, o comando pode terminar com um
erro Python não tratado (traceback, exit `1`). Veja
[Manutenção](../maintenance/maintenance.md).

### Pendências semânticas conhecidas

- O fallback de `caption` para `user_text` pode usar a apresentação do perfil
  como texto da postagem quando a legenda faltar.
- A conversão genérica para string aceita ids de qualquer tipo; o parser não
  valida que ids externos sejam numéricos.
- Um float finito é truncado para inteiro.

São limites do código atual, não garantias desejáveis.

## Serialização e testes

A CLI faz `model_dump()` em cada item e
`json.dumps(..., ensure_ascii=False, indent=2)`. Não usa `exclude_none`: campos
opcionais aparecem como `null`. A lista não inclui metadados de rota, duração,
cursor, completude ou erro; essa informação está nos logs e no código de saída.

| Teste ou artefato | Cobertura |
|---|---|
| [`tests/test_parser.py`](../../tests/test_parser.py) | URLs, autor, métricas, HTML, datas, conversões e rejeição de data fora do padrão. |
| [`tests/test_samples.py`](../../tests/test_samples.py) | Os três arquivos de [`samples/`](../../samples) validados contra `Post` e `Comment`. |
| [`tests/test_cli.py`](../../tests/test_cli.py) | JSON gerado pelos três comandos com HTTP simulado. |

Detalhes da expansão em [Comentários e respostas](../flows/comments.md).

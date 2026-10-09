[🏠 Índice](../README.md)

# Schemas e mapeamento

Este é o contrato **implementado** em [`models.py`](../../src/application/models.py),
adaptado do documento de schemas dos experimentos. Os nomes das classes foram
atualizados; os campos JSON permanecem em português. Não reproduz um schema
externo não verificado nem estabelece regras novas.

## Modelos de saída

Todos os modelos usam `extra="forbid"`. Isso rejeita campos extras ao construir
um modelo; não valida estritamente cada payload cru do Kwai nem prova a correção
semântica do mapeamento. Pydantic pode aplicar coerção de tipos.

### `Post`

| Campo | Tipo Python | Obrigatório ao construir | Observação |
|---|---|---|---|
| `id` | `str \| None` | Não | Id da postagem. |
| `url` | `str` | Sim | URL construída pelo mapper, não `HttpUrl`. |
| `autor` | `PostAuthor` | Não | Objeto vazio com campos nulos por padrão. |
| `texto` | `str \| None` | Não | Texto limpo, com entidades HTML decodificadas. |
| `data_publicacao` | `str \| None` | Não | Conversão do timestamp em milissegundos. |
| `engajamento` | `Engagement` | Sim | Métricas opcionais. |
| `coletado_em` | `str` | Sim | Timestamp gerado no início do caso de uso. |

`PostAuthor` contém `usuario`, `id`, `url_perfil`, todos `str | None`.
`Engagement` contém `curtidas`, `comentarios`, `compartilhamentos`, `visualizacoes`,
todos `int | None`. O modelo não impõe mínimo zero às métricas.

### `Comment`

| Campo | Tipo Python | Obrigatório ao construir | Observação |
|---|---|---|---|
| `id` | `str \| None` | Não | Id do comentário. |
| `postagem_url` | `str` | Sim | URL de entrada, preservada pelo caso de uso. |
| `autor` | `CommentAuthor` | Não | `usuario` e `id`, ambos opcionais. |
| `texto` | `str` | Sim | String vazia se conteúdo ausente/vazio. |
| `curtidas` | `int \| None` | Não | Contagem do comentário. |
| `data` | `str \| None` | Não | Data do comentário. |
| `coletado_em` | `str` | Sim | Mesmo carimbo aplicado à execução. |

### `ExpandedComment`

Herda `Comment` e acrescenta quatro campos com padrão `None`:

| Campo | Tipo | Raiz | Resposta |
|---|---|---|---|
| `parent_id` | `str \| None` | `null` | Id do comentário raiz. |
| `reply_to_id` | `str \| None` | `null` | Id do **usuário** respondido, não id de comentário. |
| `reply_to_usuario` | `str \| None` | `null` | Nome do usuário respondido. |
| `respostas_total` | `int \| None` | Quantidade declarada de respostas. | `null`. |

A lista é plana: raiz, suas respostas, próxima raiz. Os campos adicionais
aparecem também como `null` quando não aplicáveis. `respostas_total` não é
recalculado para caber na quantidade entregue e não significa completude.

## Exemplo sintético offline

```python
from src.application.models import Engagement, Post

post = Post(
    id="123",
    url="https://www.kwai.com/@perfil/video/123",
    engajamento=Engagement(curtidas=0),
    coletado_em="2026-10-08T00:00:00Z",
)
assert post.engajamento.curtidas == 0
assert post.engajamento.comentarios is None
print(post.model_dump())
```

JSON ilustrativo de uma raiz e uma resposta (não é uma captura real):

```json
[
  {
    "id": "r1", "postagem_url": "https://www.kwai.com/@perfil/video/123",
    "autor": {"usuario": "Autor", "id": "u1"}, "texto": "Comentário",
    "curtidas": 0, "data": null, "coletado_em": "2026-10-08T00:00:00Z",
    "parent_id": null, "reply_to_id": null, "reply_to_usuario": null,
    "respostas_total": 2
  },
  {
    "id": "s1", "postagem_url": "https://www.kwai.com/@perfil/video/123",
    "autor": {"usuario": "Outro autor", "id": "u2"}, "texto": "Resposta",
    "curtidas": null, "data": null, "coletado_em": "2026-10-08T00:00:00Z",
    "parent_id": "r1", "reply_to_id": "u1", "reply_to_usuario": "Autor",
    "respostas_total": null
  }
]
```

## Campos externos → modelo

### Feed → `Post`

| Destino | Fonte e regra atual |
|---|---|
| `id` | Primeiro não nulo: `photo_id_str`, `photo_id`; conversão para string e trim. |
| `url` | `https://www.kwai.com/@{handle}/video/{id}`; handle vem de `kwai_id` ou `user_id_str`. |
| `autor.usuario` | `@kwai_id`, se truthy; senão `user_name`. |
| `autor.id` | Primeiro não nulo: `user_id_str`, `user_id`. |
| `autor.url_perfil` | URL com o handle escolhido. |
| `texto` | Primeiro não nulo: `caption`, `user_text`; trim e `html.unescape`. |
| `data_publicacao` | `timestamp`, convertido de ms. |
| `engajamento.curtidas` | `like_count`. |
| `engajamento.comentarios` | `comment_count`. |
| `engajamento.compartilhamentos` | `forward_count`. |
| `engajamento.visualizacoes` | `view_count`. |

“Primeiro não nulo” não significa “primeiro não vazio”. Se `photo_id_str` for
string vazia, o mapper não retorna ao `photo_id` depois do trim.

### Comentário e resposta

| Destino | Fonte e regra atual |
|---|---|
| `id` | Primeiro não nulo: `comment_id`, `id`. |
| `autor.usuario`, `autor.id` | `author_name`, `author_id`. |
| `texto` | `content`, limpo e com entidades HTML decodificadas; fallback `""`. |
| `curtidas` | `liked_count`. |
| `data` | `timestamp` em ms. |
| Total declarado da raiz | `sub_comment_count`, passa por `as_int_scalar`. |
| `reply_to_id` | `reply_to`; `"0"` vira `None`. |
| `reply_to_usuario` | `replyToUserName`. |
| `parent_id` | Adicionado pela aplicação com o id da raiz sendo expandida. |

`subCommentsMap` e previews embutidos não são mesclados à saída. Não confunda a
quantidade de previews exibidos no app com o total obtido em `sublist`.

## Conversão, tolerância e rejeição

| Dado | Política implementada |
|---|---|
| Métrica ausente | `None` → `null`; não preenche com zero. |
| Escalar numérico | `int()` para int, float ou string; booleanos rejeitados. `3.9` vira `3`; string `"3.9"` não vira inteiro. |
| Escalar não conversível, infinito, NaN ou estrutura | `None` pelo helper de coerção. |
| Timestamp | Não positivo/ausente/inválido vira `None`; válido vira UTC em segundos, com `Z`. |
| `feeds` ausente/nulo | Lista vazia. |
| `feeds` não-lista | `UnexpectedResponseError`. |
| Item de feed não-objeto | Ignorado sem warning específico no mapper atual. |
| Feed sem URL montável | Ignorado com warning; restantes seguem. |
| Comentários/respostas/usuários com item não-objeto | Página inteira rejeitada, preservando páginas anteriores pela política de parcial. |

Os campos de data dos modelos são strings, não validadores `datetime`. O formato
UTC é produzido pelos helpers; construir manualmente um `Post` não garante a
mesma validação temporal usada na coleta.

### Pendências semânticas conhecidas

- O fallback de `caption` para `user_text` pode usar uma apresentação de perfil
  como texto da postagem. As amostras com caption não cobrem esse caso.
- A conversão genérica para string pode aceitar ids/nomes com tipos indevidos;
  o mapper não valida rigorosamente ids externos como strings numéricas ASCII.
- A política de truncar float finito para inteiro permanece existente.

Esses pontos são limites do código atual, não garantias desejáveis nem correções
incluídas nesta documentação.

## Serialização e testes

A CLI faz `model_dump()` e `json.dumps(..., ensure_ascii=False, indent=2)`.
Não usa `exclude_none`: campos opcionais aparecem como `null`. A lista não inclui
metadados de rota, duração, cursor, completude ou erro. Essa informação operacional
deve ser acompanhada de logs/código de saída.

| Teste/artefato | Cobertura relevante |
|---|---|
| `tests/test_models.py` | Campos obrigatórios e rejeição de extras. |
| `tests/test_parsers.py` | URLs, conteúdo, métricas, autores e datas. |
| `tests/test_response_validation.py` | Estruturas, itens, cursores e preservação do parcial. |
| `tests/test_mobile_captures.py` | Campos e cursores em recortes reais sanitizados. |
| `tests/test_samples.py`, `samples/` | Exemplos versionados compatíveis com modelos. |

Detalhes da expansão estão em [Comentários e respostas](../flows/comments.md); veja
[Referência Python](./api-reference.md) para tipos de página e exceções.

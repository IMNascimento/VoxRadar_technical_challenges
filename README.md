# Kwai Collector · Desafio VoxRadar (Nível 1)

Coletor de dados públicos do [Kwai](https://www.kwai.com/) que resolve as três
funcionalidades do desafio e gera JSON nos formatos `Postagem` e `Comentario`:

1. **Busca por palavra-chave**: postagens com link, texto e engajamento.
2. **Postagens de um usuário**: todas as postagens de um perfil.
3. **Comentários de uma postagem**: comentários a partir do link, com as
   respostas opcionais.

A coleta não precisa de login, cookies, navegador nem emulador.

## Requisitos

- **Python 3.11+**
- **[Poetry](https://python-poetry.org/)** para as dependências.

## Instalação

Com o repositório baixado, abra o terminal na pasta que contém `pyproject.toml`:

```bash
poetry install
poetry run kwai-collector --help
```

Não é preciso criar `.env`, fazer login nem fornecer cookies. A configuração
opcional está em [Primeiros passos](docs/guides/getting-started.md#configuração-opcional).

## Primeira coleta

Comece com até três postagens:

```bash
poetry run kwai-collector profile --user parkourcity --limit 3 --out out/usuario.json
```

Troque `parkourcity` pelo perfil público desejado, com ou sem `@`. O exemplo
depende da disponibilidade da API. O log mostra `3 itens salvos em
out/usuario.json`; abra esse arquivo. Sem `--out`, o JSON aparece no terminal.

## Escolha o que coletar

| Quero coletar… | Comando |
|---|---|
| Posts por palavra-chave | `search --keyword <palavra> --limit 20` (repita `--keyword` para várias) |
| Posts de um perfil | `profile --user <perfil> --limit 10` (sem `--limit`, coleta o perfil inteiro) |
| Comentários de uma postagem | `comments --url "<link>" --limit 50` |
| Comentários e respostas | Acrescente `--with-replies` ao `comments`. |

Execute com o prefixo `poetry run kwai-collector`:

```bash
# Busca por palavra-chave
poetry run kwai-collector search -k sports -k parkour -l 20 -o out/busca.json

# Posts de um usuário
poetry run kwai-collector profile -u @parkourcity -l 10 -o out/usuario.json

# Comentários de uma postagem (todos, ou os 50 primeiros)
poetry run kwai-collector comments --url "https://www.kwai.com/@parkourcity/video/5240651225143682227" -o out/comentarios.json
poetry run kwai-collector comments --url "https://www.kwai.com/@parkourcity/video/5240651225143682227" -l 50 -o out/comentarios.json

# Comentários com respostas
poetry run kwai-collector comments --url "https://www.kwai.com/@parkourcity/video/5240651225143682227" --with-replies -o out/comentarios.json
```

Também funciona como módulo: `poetry run python -m kwai_collector --help`.

**Limites:** em `search`, `--limit` é o total de posts únicos somando todas as
palavras (padrão 20). Em `profile`, conta posts únicos. Em `comments`, conta só
os comentários principais; as respostas vêm junto e não entram na conta. Sem
`--limit`, `profile` e `comments` vão até o fim informado pela API.

A busca pagina cada palavra-chave avançando o `pcursor` até atingir o limite ou
até uma página não trazer nenhum post novo. A [referência da CLI](docs/guides/cli.md) explica todas as opções.

## Saída

`--out` recebe o caminho de um arquivo JSON; as pastas são criadas e o arquivo
existente é sobrescrito. Sem `--out`, o JSON vai para o terminal (stdout) e os
logs vão para o stderr. O conteúdo é sempre uma lista JSON em UTF-8:

| Comando | Itens |
|---|---|
| `search`, `profile` | `Postagem` |
| `comments` | `Comentario` |
| `comments --with-replies` | `Comentario` com `parent_id`, `reply_to_id`, `reply_to_usuario` e `respostas_total` |

Métricas que a API não informou ficam `null`; `0` só aparece quando veio na
resposta. Há um exemplo de saída de cada funcionalidade em [`samples/`](samples/),
validado contra os modelos pelos testes. Os campos estão em
[Schemas](docs/reference/schemas.md).

### Códigos de saída

| Código | Significado |
|--------|-------------|
| `0` | Sucesso |
| `1` | Erro de coleta (rede, API, usuário não encontrado) ou falha ao gravar o arquivo |
| `2` | Entrada inválida (usuário, URL sem id, palavra-chave vazia ou opção da CLI) |

Se a coleta falhar no meio, nada é salvo: não há resultado parcial. Veja
[Falhas e códigos de saída](docs/guides/cli.md#falhas-e-códigos-de-saída).

## Documentação técnica

Para usar a ferramenta, [Primeiros passos](docs/guides/getting-started.md) e a
[CLI](docs/guides/cli.md) bastam. A referência completa está no
[índice de `docs/`](docs/README.md):

| Guia | Conteúdo |
|---|---|
| [Primeiros passos](docs/guides/getting-started.md) | Instalação, primeira coleta, configuração e problemas comuns. |
| [CLI](docs/guides/cli.md) | Comandos por objetivo, opções, destino da saída e falhas. |
| [Referência Python](docs/reference/api-reference.md) | Funções, exceções e uso a partir de outro programa. |
| [Arquitetura](docs/internals/architecture.md) | Módulos, dependências e ciclo de uma execução. |
| [Assinatura e sal](docs/internals/signature.md) | Fórmula do `sig`, identidade do app e vetor de prova. |
| [Protocolo móvel](docs/internals/mobile-api.md) | Rotas, campos, contextos, hosts e retry. |
| [Schemas](docs/reference/schemas.md) | Campos JSON e mapeamento a partir da API. |
| [Regras de negócio](docs/business-rules/README.md) | Políticas de coleta, dados e falhas. |
| [Fluxos](docs/flows/README.md) | Ciclo de vida, operações e paginação em diagramas. |
| [Casos de uso](docs/use-cases/README.md) | Entradas, passos, alternativas e resultados por operação. |
| [ADRs](docs/adr/README.md) | Decisões adotadas e seus trade-offs. |
| [Manutenção](docs/maintenance/maintenance.md) | Diagnóstico, testes, smoke e atualização de versão. |
| [Pesquisa](docs/maintenance/research.md) | Origem da solução, evidências e questões em aberto. |

## Configuração

Tipada com `pydantic-settings`, lida do `.env` e do ambiente (prefixo `KWAI_`).
Veja [`.env.example`](.env.example). Nenhum segredo é necessário.

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `KWAI_REQUEST_DELAY` | `1.5` | Intervalo mínimo (s) entre requisições (rate limit). |
| `KWAI_HTTP_TIMEOUT` | `20` | Timeout de cada requisição HTTP (s). |
| `KWAI_MAX_RETRIES` | `3` | Tentativas extras em falha passageira, com backoff exponencial. |
| `KWAI_USER_AGENT` | *(navegador)* | User-Agent da busca web; a API móvel usa o do app. |

## Como rodar os testes

Os testes **não dependem de rede**: o HTTP é simulado com `respx`, e o delay e
o backoff são zerados. Usam respostas reais recortadas em
[`tests/fixtures/`](tests/fixtures/README.md).

```bash
poetry run pytest
```

## Qualidade de código

```bash
poetry run ruff check .           # lint
poetry run ruff format --check .  # formatação
poetry run mypy                   # tipagem estática (strict)
```

## Arquitetura

O pacote `kwai_collector` é dividido em módulos por responsabilidade, sem
camadas. Detalhes em [Arquitetura](docs/internals/architecture.md) e na
[ADR-0003](docs/adr/0003-flat-modules.md).

| Módulo | Papel |
|--------|-------|
| `cli.py` | Comandos Typer, logging, códigos de saída e escrita do JSON. |
| `scraper.py` | Busca, perfil, comentários e respostas: paginação, limites e deduplicação. |
| `client.py` | HTTP: rate limit, retry com backoff, troca de host, assinatura `sig` e checagem do campo `result`. |
| `parser.py` | Converte o JSON do Kwai nos modelos (números, datas, texto, URLs). |
| `models.py` | Modelos Pydantic de saída (`Postagem` e `Comentario`). |
| `config.py` | Configuração tipada (`Settings`). |

## Decisões de engenharia

O Kwai carrega o conteúdo dinamicamente e usa endpoints diferentes por
funcionalidade. A escolha foi **consumir os endpoints HTTP** em vez de
automatizar um navegador: é mais leve e mais rápido.

- **Busca:** `POST /rest/o/w/pwa/v2/search/word/outer`, endpoint JSON do site.
  Pagina por deslocamento: o `pcursor` do corpo avança de `count` em `count`
  (até 50 por página). A API não devolve cursor nem lista vazia; quando a
  palavra se esgota, repete itens, então a paginação para na primeira página
  sem post novo. Várias palavras são consultadas em ordem e os resultados são
  deduplicados por `id`.
- **Postagens de usuário:** API móvel anônima, em dois passos.
  `POST /rest/o/user/getInfo` resolve o usuário no id numérico e
  `POST /rest/o/feed/profile` entrega as páginas por `pcursor` (30 por página).
- **Comentários:** `POST /rest/o/comment/list/v2` na API móvel anônima (50 por
  página), e `POST /rest/o/comment/sublist` para as respostas (100 por página).
- **Assinatura:** as rotas móveis exigem o parâmetro `sig`, um MD5 dos
  parâmetros (query + corpo) em ordem alfabética, sem separador, com o sal do
  app no fim. Ele é calculado em Python e validado contra o `sig` de um request
  real do app (vetor em `tests/test_client.py`). O sal só foi provado para a
  versão `10.3.20.539600` do Kwai Lite. Detalhes em
  [Assinatura](docs/internals/signature.md).

### Resiliência

- **Rate limit** configurável: intervalo mínimo entre todas as requisições.
- **Retry com backoff** em falha passageira (rede, `429`, `5xx`, resposta que
  não é JSON). Outros status de erro e erros de negócio (`result != 1`) não são
  repetidos.
- **Troca de host:** a API móvel tem três hosts equivalentes; se um falhar,
  tenta o próximo antes de repetir a rodada.
- **Paginação completa e deduplicação** na busca, no perfil, nos comentários e
  nas respostas, com proteção contra cursor repetido e, na busca, contra página
  sem post novo.

### Limitações conhecidas

- A **busca** não informa quando acabou: a API repete itens em vez de devolver
  lista vazia. O coletor considera a palavra esgotada na primeira página sem
  post novo.
- **Fim de cursor não prova completude:** em uma observação, um comentário
  declarava 59 respostas e a API entregou 52 antes de indicar o fim. O campo
  `respostas_total` mostra o número declarado.
- **Tudo ou nada:** se a coleta falhar no meio, nada é salvo. Para perfis
  grandes (um com 7.389 posts levou cerca de 6 minutos), use `--limit` ou
  aumente `KWAI_MAX_RETRIES`.
- O sal do `sig` vale para a versão `10.3.20.539600` do app. Se o Kwai deixar de
  aceitar, é preciso capturar um request novo e atualizar `APP_VERSION` e
  `SIG_SALT`. Veja [Manutenção](docs/maintenance/maintenance.md).
- `__NS_sig3` não é reproduzido; as rotas usadas funcionam sem ele.

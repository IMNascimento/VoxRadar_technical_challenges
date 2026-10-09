# Kwai Collector · Desafio VoxRadar

Coletor de dados públicos do [Kwai](https://www.kwai.com/) que resolve as três
funcionalidades do desafio, produzindo JSON aderente aos schemas `Postagem` e
`Comentario`:

1. **Busca por palavra-chave** — postagens com link, texto e engajamento.
2. **Postagens de um usuário** — postagens de um perfil.
3. **Comentários de uma postagem** — comentários a partir do link.

## Requisitos

- **Python 3.11+**
- **[Poetry](https://python-poetry.org/)** para gestão de dependências.

Sem runtime externo: tudo roda em Python puro (sem Node, sem navegador headless).

## Instalação

Com o repositório baixado, abra o terminal na pasta que contém `pyproject.toml`:

```bash
poetry install
poetry run kwai-collector --help
```

Não é necessário criar `.env`, fazer login ou fornecer cookies para começar.
Configuração opcional e instruções para PowerShell estão em [Primeiros passos](docs/guides/getting-started.md).

## Primeira coleta

Comece com até três postagens, sem expandir comentários:

```bash
poetry run kwai-collector profile --user parkourcity --limit 3
```

Troque `parkourcity` pelo perfil público desejado, com ou sem `@`. O exemplo
depende da disponibilidade da API; não garante que o perfil tenha posts.
O terminal informa `Export directory: ...`. Abra `posts.json` nessa pasta:

```text
exports/parkourcity/<execução>/posts.json
```

`exports/` é criada no diretório onde você executou o comando. Cada coleta usa
uma pasta de execução diferente. Não precisa informar `--out`.

## Escolha o que coletar

| Quero coletar… | Comando/opção |
|---|---|
| Posts de um perfil | `profile --user <perfil> --limit 10` |
| Posts e comentários sem respostas | Acrescente `--with-comments`. |
| Posts e comentários com respostas | Acrescente `--with-comments-replies`. |
| As duas versões dos comentários | Use ambas as opções. |
| Posts por palavra-chave | `search --keyword <palavra> --limit 20` |
| Ordenar os posts coletados do maior para o menor | Em `profile`/`search`, acrescente `--sort-by likes`, `comments`, `shares` ou `views`. |
| Comentários de uma única postagem | `comments --url "<link>" --limit 50` |

Execute os comandos com o prefixo `poetry run kwai-collector`, como nos exemplos:

Os comandos recomendados são `search`, `profile` e `comments`. Sem `--out`,
exportam automaticamente para `exports/`. `--out/-o` indica uma **pasta-base**,
não um arquivo. Veja a [referência da CLI](docs/guides/cli.md) para opções e parciais.

```bash
# Busca por palavra-chave (repita -k para várias palavras)
poetry run kwai-collector search -k sports -k parkour -l 20

# Perfil: posts, versão simples ou versão expandida por postagem
poetry run kwai-collector profile -u parkourcity -l 10
poetry run kwai-collector profile -u parkourcity -l 10 --with-comments
poetry run kwai-collector profile -u parkourcity -l 10 --with-comments-replies --comments-limit 50
poetry run kwai-collector profile -u parkourcity -l 10 --with-comments --with-comments-replies -o exports-custom

# Comentários e respostas de uma postagem
poetry run kwai-collector comments --url "https://www.kwai.com/@parkourcity/video/5240651225143682227" --limit 50 --with-comments-replies
```

**Limites:** em `profile`, `--limit` conta posts e `--comments-limit` conta
comentários raiz por postagem, antes do dedupe. Respostas não consomem esse
limite. Sem limites, perfil/comentários continuam até o fim informado pela API;
por isso, use tetos pequenos nas primeiras coletas.

Para ordenar por uma contagem individual:

```bash
poetry run kwai-collector profile -u parkourcity -l 100 --sort-by likes
poetry run kwai-collector search -k sports -l 20 --sort-by views
```

Ordena somente os posts obtidos pelo limite, não o perfil inteiro. Valores
desconhecidos ficam no fim. Sem `--sort-by`, a ordem original é preservada.

## Onde os arquivos ficam

Saída: `exports/<perfil>/<execução>/posts.json`, `comments/<post-id>.json` e/ou
`comments-replies/<post-id>.json`. A versão expandida repete as raízes e inclui
respostas com vínculo explícito; não há pasta só de respostas. `search` usa
`exports/search/<execução>/`; `comments` não cria `posts.json`.

Também funciona como módulo: `poetry run python -m src --help`.

### Códigos de saída

| Código | Significado |
|--------|-------------|
| `0` | Sucesso |
| `1` | Erro de execução/coleta (rede, API). Se a falha vier no meio da coleta, o que já foi coletado é gravado na saída (parcial) antes de sair |
| `2` | Entrada inválida (URL fora do padrão, usuário inválido) |

Arquivos com `.partial.json` indicam uma coleta interrompida. Se ocorrer erro
de escrita, nem o parcial tem persistência garantida. Veja [Falhas e parciais](docs/guides/cli.md#falhas-e-parciais).

## Documentação técnica

Para usar a ferramenta, [Primeiros passos](docs/guides/getting-started.md) e
[CLI e exportação](docs/guides/cli.md) são suficientes; não é necessário estudar a API
móvel ou a assinatura antes de coletar. A referência completa está no
[índice de `docs/`](docs/README.md):

| Guia | Conteúdo |
|---|---|
| [Primeiros passos](docs/guides/getting-started.md) | Instalação, primeira coleta e configuração opcional. |
| [CLI e exportação](docs/guides/cli.md) | Comandos por objetivo, opções, pastas e parciais. |
| [Referência Python](docs/reference/api-reference.md) | Integração, casos de uso, portas e exceções. |
| [Assinatura e sal](docs/internals/signature.md) | Fórmula do `sig`, identidade do app e vetores de prova. |
| [Protocolo móvel](docs/internals/mobile-api.md) | Rotas, campos, contextos, gateways e retry. |
| [Schemas](docs/reference/schemas.md) | Campos JSON e mapeamento. |
| [Regras de negócio](docs/business-rules/README.md) | Políticas de coleta, dados e falhas. |
| [Fluxos](docs/flows/README.md) | Ciclo de vida, operações, paginação e parcial. |
| [Casos de uso](docs/use-cases/README.md) | Entradas, passos, alternativas e resultados por operação. |
| [ADRs](docs/adr/README.md) | Decisões adotadas e seus trade-offs. |
| [Manutenção](docs/maintenance/maintenance.md) | Diagnóstico, atualização e testes. |
| [Pesquisa](docs/maintenance/research.md) | Experimentos adaptados, histórico e limites de evidência. |

## Configuração (variáveis de ambiente)

Tipada via `pydantic-settings`, lida de `.env` e do ambiente (prefixo `KWAI_`).
Veja [`.env.example`](.env.example). Nenhum segredo é obrigatório.

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `KWAI_REQUEST_DELAY` | `1.5` | Intervalo mínimo (s) por adapter: por tentativa web ou rodada móvel. |
| `KWAI_HTTP_TIMEOUT` | `20` | Timeout HTTP (s). |
| `KWAI_MAX_RETRIES` | `3` | Tentativas extras em falhas transitórias (backoff exponencial), na busca e na API móvel. |
| `KWAI_USER_AGENT` | *(navegador)* | User-Agent das requisições web (só a busca; a API móvel usa o UA do app). |

## Como rodar os testes

Os testes **não dependem de rede** (HTTP mockado com `respx`) nem de nenhum
runtime externo, e o backoff do retry é neutralizado nos testes (sem `sleep`
real). Há também testes de regressão com recortes sanitizados de capturas reais
da API móvel (`tests/integration/test_mobile_captures.py`).

```bash
poetry run pytest                 # suíte completa
poetry run pytest --cov=src --cov-report=term-missing
```

## Qualidade de código

```bash
poetry run ruff check .           # lint
poetry run ruff format --check .  # formatação
poetry run mypy src    # tipagem estática (strict)
```

## Arquitetura

Pacote organizado em DDD tático com Ports & Adapters; a composição dos serviços
fica em `infrastructure/container/container.py`. Detalhes em
[Arquitetura](docs/internals/architecture.md).

| Camada | Módulos principais | Papel |
|--------|--------------------|-------|
| `shared/` | `logging/logging_config` | Configuração de logging compartilhada pelas camadas. |
| `domain/` | `entities/`, `value_objects/`, `enums/`, `exceptions/`, `services/` (`identity`, `post_urls`, `replies`, `pagination`, `post_ordering`) | Entidades do contrato (`Post`, `Comment`, `ExpandedComment`), value objects (`Handle`, `UserId`, `PhotoId`, `PostReference`, `Cursor`, `IsoTimestamp`), `PostSortBy`, exceções e regras puras de identidade/dedup, formato das URLs do Kwai, expansão e contagem de respostas, paginação e ordenação. |
| `application/` | `ports/`, `dtos/` (`commands`, `pages`, `collection_result`), `use_cases/` (`search_posts`, `collect_user_posts`, `collect_comment_versions`, `collect_profile_bundle`), `exceptions` | Portas de saída (`ISearchApiPort`, `IProfileApiPort`, `ICommentApiPort`, `IClockPort`), comandos de entrada validados, páginas e resultado por unidade, casos de uso e a exceção de coleta interrompida (carrega o resultado parcial). |
| `infrastructure/` | `container/`, `clock/`, `kwai/` (`web/` e `mobile/` com `client` e `adapter`; `app_identity`, `signature`, `mapping`, `coercion`, `http_utils`, `business_result`, `ratelimit`, `exceptions`) | Composição, relógio do sistema e acesso HTTP (web: busca; móvel anônima: comentários e perfil), com cliente (sessão, rate limit, retry) separado do adapter (rota, contexto, tamanho de página), identidade do app (versão, `client_key` e sal do `sig`, que valem juntos), assinatura `sig` (MD5 + sal), conversão dos dados crus (escalares e timestamps em ms), JSON/retry, validação do campo `result`, relógio do sistema e exceções de transporte, resposta inesperada e erro de negócio. |
| `entrypoints/` | `cli/` (`app`, `export_commands`, `export_files`) | CLI e comandos de exportação organizada por diretório. |
| `config/` | `settings` | Configuração tipada via ambiente (`Settings`). |
| raiz | `__main__.py` | Ponto de entrada (`python -m src` e script `kwai-collector`). |

## Decisões de engenharia

O Kwai carrega conteúdo dinamicamente e usa endpoints diferentes por
funcionalidade. Optei por **consumir os endpoints HTTP que a própria página
usa** (mais leve e rápido que automatizar um navegador), com uma exceção
justificada:

- **Busca** — `POST /rest/o/w/pwa/v2/search/word/outer`. Endpoint JSON público.
  **Não usa cursor**: retorna um lote único de até ~50 itens por palavra-chave
  (a partir daí a API responde erro). A CLI aceita **múltiplas palavras-chave**
  e **deduplica** os resultados por `id`; `--limit` é o **teto do total final
  após dedupe entre as palavras-chave** (não por palavra-chave).
- **Postagens de usuário** — vêm da **API móvel anônima**, em dois passos:
  `POST /rest/o/user/getInfo` resolve o handle no id numérico (o feed **não**
  aceita handle) e `POST /rest/o/feed/profile` entrega as páginas por `pcursor`
  (`count=30`). A assinatura é a mesma dos comentários (`sig`), mas **o contexto
  usado difere por rota**: o `getInfo` usa o contexto **completo** do app e o
  feed usa o **mínimo validado no coletor**. O app também obteve postagens com
  contexto completo; respostas vazias anteriores não provam rejeição universal.
  Atenção: a rota **web** de paginação (`POST /rest/o/w/pc/feed/profile`) não
  entregou a paginação anônima nos testes históricos e **não** é usada. Não
  confunda seu caminho com o da rota móvel.
- **Comentários** — `POST /rest/o/comment/list/v2` na **API móvel anônima**
  (gateway primário `api.kwai-pro.com`, com fallback automático entre gateways
  equivalentes): sem login, sem cookies e sem `__NS_sig3`. A requisição é
  assinada com o `sig` — MD5 dos parâmetros (query + corpo) ordenados, sem
  separador, com valores já decodificados, + sal `382700b563f4` — reproduzido em
  Python puro em `infrastructure/kwai/mobile/signature.py` (`compute_sig`) e validado por **match exato**
  contra o `sig` do app real (vetor de regressão em `tests/integration/test_mobile_api.py`). O sal
  só foi provado para a versão do app em `infrastructure/kwai/mobile/app_identity.py`;
  não há garantia para outras versões. Um teste associa versão e vetor.
  As **respostas** de cada comentário vêm de `POST /rest/o/comment/sublist`
  (mesmo contexto e assinatura; `rootCommentId` + `client_key`) e são expostas
  com o comando `comments --with-comments-replies`.
  O contexto enviado é o **completo do app** (emulação máxima), com `count=50`
  por página e `timestamp`/`session_id` gerados por requisição; a paginação usa
  `pcursor` (`no_more` = fim) com deduplicação. Há uma **escada de fallback**
  entre gateways, sem reduzir automaticamente o contexto. A rota web
  (`/rest/o/w/pc/getComments/list`) não entregou a lista anônima esperada nos
  testes históricos e **não** é usada. Detalhes em [Protocolo móvel](docs/internals/mobile-api.md) e
  [Assinatura](docs/internals/signature.md); evidências em [Pesquisa](docs/maintenance/research.md).

### Resiliência

- **Retry com backoff** (`KWAI_MAX_RETRIES`): na busca, em `429`/`5xx`/falha de
  rede; na API móvel, repetindo a escada de gateways inteira quando **todos**
  falham no transporte. Erro de negócio (`result != 1`) **nunca** é repetido.
- **Resultado parcial**: se a coleta falha no meio (rede, cursor em laço), os
  itens anteriores ficam no parcial em memória. A CLI tenta gravá-los e sai com
  código `1`; uma falha de escrita impede a garantia de persistência. Sem nada
  coletado, não cria uma nova saída; arquivos antigos no destino não são removidos.
- **Respostas de comentários**: uma raiz cuja sublista entra em laço de cursor é
  registrada no log e as demais seguem.
  Com `--with-comments-replies`, diferenças entre respostas declaradas e efetivamente
  coletadas geram aviso com ambas as contagens, sem atribuir uma causa. O aviso
  não altera o JSON nem o código de saída; `respostas_total` continua declarado.

### Limitações conhecidas

O coletor entrega o **máximo confirmado sem autenticação**:

- **Busca** não tem paginação por cursor no endpoint público (teto ~50/keyword).
- **Postagens de usuário**: coleta **anônima e paginada** via API móvel,
  paginada por `pcursor` (30 por página). O teto de ~20 itens era a via SSR, que
  foi removida.
- **Comentários**: coleta **anônima e paginada** via API móvel, com rate limit.
  Fim de cursor é o fim informado pela API, não prova de completude: em uma
  observação, 59 respostas foram declaradas e 52 entregues com `no_more`.
  Não foi determinada a causa. O algoritmo de `__NS_sig3` não foi reproduzido;
  as rotas atuais funcionaram sem ele. A hipótese `atlasSign(caminho + sig)`
  não descreve as entradas maiores observadas no app.

### Investigação histórica

A via web de perfil e a coleta SSR foram investigadas antes da adoção da rota
móvel. As chamadas web anônimas examinadas não permitiram a paginação desejada;
o parser Nuxt foi removido. Não deduza a política inteira de autorização do
servidor a partir de um código de negócio isolado.

O [registro de pesquisa](docs/maintenance/research.md) resume essa evolução, as alternativas
abandonadas e as correções de hipóteses antigas. A implementação atual de perfil
usa exclusivamente `getInfo` e `feed/profile` móveis.

## Aderência ao contrato

A saída segue as entidades do domínio (`domain/entities/`). Campos ausentes
viram `null` (nunca inventados); métricas de engajamento só são `0` quando o
valor é comprovadamente zero. Datas em ISO-8601 (UTC, sufixo `Z`);
`coletado_em` marca o momento da coleta.

Amostras em [`samples/`](samples), todas validadas contra os schemas:

| Arquivo | Origem |
|---------|--------|
| `busca.json` | Coleta real por palavra-chave (`sports`, limite 5). |
| `usuario.json` | Coleta real do perfil `@parkourcity` (limite 5). |
| `comentarios.json` | Coleta real anônima de comentários (limite 5, via API móvel). |

## Manutenção

A coleta depende de duas superfícies do Kwai: busca web e API móvel assinada.
O [runbook local](docs/maintenance/maintenance.md) detalha diagnóstico, smoke, revisão de
contexto, assinatura, atualização de versão e promoção de fixtures sanitizadas.
Não assuma que uma quebra seja mudança de sal: preserve rota, mensagem,
`result`, contagens e código de saída antes de formular a causa.

A documentação adapta os experimentos ao pacote atual, distinguindo observação
de hipótese. Emulador e Frida podem ajudar uma investigação autorizada, mas não
integram o fluxo de coleta. Os exemplos Python usam os imports reais `src.*`;
não é necessário instalar uma biblioteca de terceiros com nome parecido.

## Ética e legalidade

Coleta apenas conteúdo público, respeitando um rate limit configurável.
Nenhuma credencial é versionada (`.env` no `.gitignore`). Use conforme os
Termos de Uso do Kwai e a legislação aplicável (ex.: LGPD).

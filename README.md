# Kwai Collector · Desafio VoxRadar (Nível 1)

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

```bash
poetry install
cp .env.example .env   # opcional; há padrões seguros
```

## Uso

As três funcionalidades são subcomandos da CLI. Todos aceitam `--out/-o`
(arquivo de saída; sem ele, imprime no stdout), `--limit/-l` e `--verbose/-v`.

```bash
# 1) Busca por palavra-chave (repita -k para várias palavras)
poetry run kwai-collector busca --keyword "sports" --limit 30 --out out/busca.json
poetry run kwai-collector busca -k "eleicoes" -k "politica" -o out/busca.json

# 2) Todas as postagens de um usuário
poetry run kwai-collector usuario --user "@parkourcity" --out out/usuario.json

# 3) Comentários de uma postagem
poetry run kwai-collector comentarios \
  --url "https://www.kwai.com/@parkourcity/video/5240651225143682227" \
  --out out/comentarios.json

# 3b) Comentários + respostas (lista plana com parent_id/reply_to_*)
poetry run kwai-collector comentarios \
  --url "https://www.kwai.com/@parkourcity/video/5240651225143682227" \
  --com-respostas --out out/comentarios_respostas.json
```

Também funciona como módulo: `poetry run python -m src --help`.

### Códigos de saída

| Código | Significado |
|--------|-------------|
| `0` | Sucesso |
| `1` | Erro de execução/coleta (rede, API, avaliação SSR) |
| `2` | Entrada inválida (URL fora do padrão, usuário inválido) |

## Configuração (variáveis de ambiente)

Tipada via `pydantic-settings`, lida de `.env` e do ambiente (prefixo `KWAI_`).
Veja [`.env.example`](.env.example). Nenhum segredo é obrigatório.

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `KWAI_REQUEST_DELAY` | `1.5` | Intervalo mínimo (s) entre requisições (rate limit). |
| `KWAI_HTTP_TIMEOUT` | `20` | Timeout HTTP (s). |
| `KWAI_MAX_RETRIES` | `3` | Tentativas extras em falhas transitórias (backoff exponencial). |
| `KWAI_USER_AGENT` | *(navegador)* | User-Agent das requisições web (busca e perfil). |

## Como rodar os testes

Os testes **não dependem de rede** (HTTP mockado com `respx`) nem de nenhum
runtime externo: a avaliação do estado SSR é feita em Python puro e coberta por
fixtures. A suíte tem **104 testes**.

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

Pacote organizado em camadas (DDD-leve), com a composição dos serviços no
`container.py`:

| Camada | Módulos principais | Papel |
|--------|--------------------|-------|
| `shared/` | `logging_config`, `utils/` (`coercion`, `timestamps`, `signature`, `ratelimit`) | Utilitários técnicos reutilizáveis: configuração de logging e helpers de coerção, timestamps ISO-8601, assinatura `sig` (MD5 + sal) e rate limit. |
| `domain/` | `identity`, `business_result`, `constants`, `exceptions`, `value_objects/` | Identidade e chaves de dedup, validação da regra de negócio `result`, constantes (`BASE_URL`), exceções e value objects (`Handle`, `PhotoId`, `Cursor`, `IsoTimestamp`). |
| `application/` | `models`, `ports`, `search_posts`, `collect_user_posts`, `collect_comments` | Contrato `pydantic` da saída (schemas), portas (*seams* de I/O) e os três casos de uso. |
| `infrastructure/` | `web_client`, `mobile_client`, `nuxt`, `mapping`, `http_utils`, `exceptions` | Acesso HTTP (web e API móvel anônima), parser do estado SSR (`__NUXT__`) em Python puro, conversão dos dados crus, decodificação de JSON e exceções de transporte/inesperadas. |
| `entrypoints/` | `cli.py` | Interface de linha de comando (Typer). |
| raiz | `config.py`, `container.py`, `__main__.py` | Configuração tipada via ambiente, composição dos serviços (`build_services`) e ponto de entrada. |

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
- **Postagens de usuário** — as postagens do perfil **não** têm endpoint JSON
  anônimo. O endpoint real é `POST /rest/o/w/pc/feed/profile` (chamado no bundle
  via `$axios.$$post("overseaAPI::/rest/o/w/pc/feed/profile", …)`) e **exige
  sessão logada**: para anônimos responde `result: 11`. Investiguei o gate a
  fundo (ver [Investigação do endpoint de perfil](#investigação-do-endpoint-de-perfil))
  e **não é uma assinatura forjável** — é autenticação da plataforma. Porém a
  página do perfil (SSR/Nuxt) **já embute a primeira página de postagens** no
  estado `window.__NUXT__`. Esse estado é uma IIFE minificada da forma
  `(function(a,b,…){return {…}}(…))` — um *object literal* de JS cujos valores
  repetidos são fatorados em parâmetros da função. Em vez de avaliá-lo com um
  interpretador JS (Node/V8) ou um navegador headless, **resolvo a expressão com
  um pequeno parser recursivo em Python puro** (`infrastructure/nuxt.py`): sem dependências, sem
  processos externos, testável offline e com saída validada campo a campo contra
  um `eval` real.
- **Comentários** — `POST /rest/o/comment/list/v2` na **API móvel anônima**
  (gateway primário `api.kwai-pro.com`, com fallback automático entre gateways
  equivalentes): sem login, sem cookies e sem `__NS_sig3`. A requisição é
  assinada com o `sig` — MD5 dos parâmetros (query + corpo) ordenados, sem
  separador, com valores já decodificados, + sal `382700b563f4` — reproduzido em
  Python puro em `shared/utils/signature.py` (`compute_sig`) e validado por **match exato**
  contra o `sig` do app real (vetor de regressão em `tests/test_mobile_api.py`).
  As **respostas** de cada comentário vêm de `POST /rest/o/comment/sublist`
  (mesmo contexto e assinatura; `rootCommentId` + `client_key`) e são expostas
  com o comando `comentarios --com-respostas`.
  O contexto enviado é o **completo do app** (emulação máxima — configuração da
  fonte da verdade, o `kwai-pure`), com `count=50` por página e `timestamp`/
  `session_id` gerados por requisição; a paginação usa `pcursor` (`no_more` = fim)
  com deduplicação. Há uma **escada de fallback** documentada (reduzir para
  `kpn`/`appver` + corpo mínimo) caso o gateway endureça. A rota web
  (`/rest/o/w/pc/getComments/list`) é *login-gated* para visitantes e **não** é
  usada. Detalhes, evidências e runbook: `solucao_api_movel_anonima.md`
  (documento de pesquisa, mantido fora deste repositório).

### Limitações conhecidas

O coletor entrega o **máximo confirmado sem autenticação**:

- **Busca** não tem paginação por cursor no endpoint público (teto ~50/keyword).
- **Postagens de usuário**: o SSR entrega a primeira página (~20 itens). Ir além
  exige **sessão logada** (não é forjável — ver investigação abaixo).
- **Comentários**: coleta **anônima e completa** via API móvel, com paginação e
  rate limit. Só queda de rede/serviço interrompe.

### Investigação do endpoint de perfil

Antes de aceitar a limitação dos ~20 itens, investiguei o gate do endpoint de
paginação (`/rest/o/w/pc/feed/profile`) capturando o tráfego real da página:

1. **Não é assinatura de cliente.** A requisição real que a página emite tem
   **URL limpa** (sem parâmetro de assinatura na query) e envia **apenas** os
   cabeçalhos `Accept` e `Content-Type` — nenhum header tipo `__NS_sig3`.
2. **A própria função assinada da página falha anônima.** Invocando o poster
   interno do app (`$nuxt.$axios.$$post`, o mesmo que assina todas as chamadas):
   a **busca pública** retorna `result: 1`, mas `feed/profile` retorna
   `result: 11`. Como ambos passam pelo mesmo assinador, a diferença **não** é a
   assinatura.
3. **O SSR ignora paginação por query.** `?pcursor=`, `?cursor=` e `?page=2`
   retornam sempre a mesma primeira página.
4. **Cookies anônimos não bastam.** Reusando via HTTP puro os cookies que o Kwai
   emite numa visita anônima (`kpn`, `apptype`, `sys`, `client_type`, `bucket`,
   `client_key`, `i18n_redirected`, `countryInfo` — nenhum é token de sessão),
   `feed/profile` ainda responde `result: 11`.

**Conclusão:** o gate é **sessão autenticada (login real)** — o servidor exige um
token de sessão que só emite após login e valida do próprio lado. Não é uma
assinatura de cliente forjável, e um token de sessão **não pode ser fabricado
sem login** (seria burlar a autenticação do serviço). Sem login, os ~20 itens do
SSR são o teto real — e é o que o coletor entrega.

## Aderência ao contrato

A saída é validada pelos modelos `pydantic` (`application/models.py`). Campos ausentes
viram `null` (nunca inventados); métricas de engajamento só são `0` quando o
valor é comprovadamente zero. Datas em ISO-8601 (UTC, sufixo `Z`);
`coletado_em` marca o momento da coleta.

Amostras em [`samples/`](samples), todas validadas contra os schemas:

| Arquivo | Origem |
|---------|--------|
| `busca.json` | Coleta real (`busca -k sports -l 5`). |
| `usuario.json` | Coleta real (`usuario -u @parkourcity -l 5`). |
| `comentarios.json` | Coleta real anônima (`comentarios -l 5`, via API móvel). |

## Manutenção

A coleta depende de três superfícies do Kwai: o endpoint de busca, o SSR do
perfil e a API móvel assinada. O runbook completo — detecção por código
`result`, re-derivação do `sig` em minutos, cadência e fallbacks — está em
`solucao_api_movel_anonima.md` §8 (documento de pesquisa, mantido fora deste
repositório).
Resumo: rode as três funcionalidades com `-l 2`; se os dados pararem de sair,
siga o runbook (a causa mais provável é o sal do `sig` mudar).

## Ética e legalidade

Coleta apenas conteúdo público, respeitando um rate limit configurável.
Nenhuma credencial é versionada (`.env` no `.gitignore`). Use conforme os
Termos de Uso do Kwai e a legislação aplicável (ex.: LGPD).

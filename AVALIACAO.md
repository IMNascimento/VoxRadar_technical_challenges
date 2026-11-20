# Avaliação · Desafio Kwai · Nível 1 · Lucas7721 (versão DDD)

**PR:** #5 · **Branch:** `solution/kwai-nivel1-lucas7721-ddd` · **Data:** 2026-11-20

| | |
|---|---|
| Nota base (critérios ponderados + bônus) | **88.75** |
| Penalização por uso de IA (−25% da nota base) | não se aplica |
| **Nota final** | **88.75 / 100** |

## Como a nota foi calculada
Método do `docs/avaliacao.md`: cada critério recebe nota 0–4 e a nota final é a soma de (peso × nota/4), mais o bônus. O nível escolhido é o contrato: avaliamos contra os requisitos do Nível 1. Foco da avaliação: solução, código escrito e README de instalação e execução.

---


## (a) Resumo

Coletor em Python (Typer + httpx + pydantic-settings + tenacity) com três comandos (`search`, `profile`, `comments`). Funciona contra o Kwai real. A instalação seguiu o README sem nenhum passo faltando, e as três funcionalidades rodaram e geraram JSON aderente ao schema. A qualidade das ferramentas é muito boa: 302 testes passando com 99% de cobertura e sem rede, `ruff check`, `ruff format --check` e `mypy --strict src` limpos, e pydocstyle ativo via ruff (`D`).

O ponto fraco é a proporção. O Nível 1 pede módulos separados (client/parser/models/cli). A solução entrega DDD tático completo, com 69 arquivos de código (~3.200 linhas), 89 com os testes, e ~3.000 linhas de docs em 32 arquivos. Isso é excesso em relação ao nível declarado. Há ainda uma fragilidade de fundo: perfil e comentários dependem da API móvel assinada por engenharia reversa (sal fixo + identidade falsa de app Android). Funciona hoje, mas é frágil e arriscada em termos de termos de uso.

Não há segredo commitado. O sal `382700b563f4` em `app_identity.py:17` é uma constante pública do app extraído por engenharia reversa, não uma credencial do usuário. `.env` está no `.gitignore` e só `.env.example` está no repositório.

## (b) Evidência de execução

Ambiente: venv isolado em `scratchpad/venvs/pr5`, `poetry install` com `VIRTUAL_ENV` apontando para ele.

- Falha de instalação: nenhuma. O `poetry.toml` do candidato tem `in-project=true`. Minha primeira tentativa criou um venv em `~/.cache/pypoetry`, que removi, e refiz com `VIRTUAL_ENV`. Isso foi erro meu, não do candidato.
- `poetry run kwai-collector --help` funciona e lista os 3 comandos. `python -m src --help` também existe.
- `pytest --cov=src`: **302 passed**, cobertura **99%** (1.217 stmts, 12 faltando). Só `__main__.py` tem 0%. Rodou em 6,8 s, sem rede (respx).
- `ruff check .`: All checks passed. `ruff format --check .`: 89 files already formatted.
- `mypy src` (strict + plugin pydantic): **Success, 69 files**.
- `mypy tests` (não documentado no README): **8 erros**, todos em `tests/unit/test_usecases.py` (linhas 153, 236, 258, 278, 336, 337, 359). Os testes não estão tipados de forma limpa.
- `print(` em `src/`: nenhum. Só `typer.echo("Export directory: ...")` na CLI, que é saída de usuário.

Execuções reais (cwd isolado):

| Comando | Resultado |
|---|---|
| `profile -u parkourcity -l 3` | exit 0, 3 posts, ~2,5 s. `exports/parkourcity/<ts>-<id>/posts.json` |
| `profile -u parkourcity -l 70` | exit 0, 70 posts únicos (paginação por `pcursor`, 30 por página), 0 duplicados |
| `search -k sports -k parkour -l 12 --sort-by likes` | exit 0, 12 posts. Só `sports` foi consultada: o limite foi atingido antes de `parkour`. Está documentado |
| `search -k sports -k parkour -l 80 --sort-by views` | exit 0, 80 posts. A busca trouxe 100 únicas e cortou em 80 |
| `search -k parkour -k futebol -l 200` | exit 0, 200 posts únicos (5 páginas), 0 duplicados. 1 WARNING `feed ignorado: feed sem photo_id/handle` (item descartado com log) |
| `comments --url .../@parkourcity/video/5240651225143682227 --limit 5` | exit 0, 5 comentários em `comments/<id>.json` |
| `comments --url .../5230518122703508277 --with-comments-replies` | exit 0, 23 registros em `comments-replies/<id>.json` |
| `profile -u parkourcity -l 70 --with-comments --comments-limit 5` | exit 0, 70 posts + 70 arquivos de comentários. Cada post leva ~1,5 s de rate limit |
| `profile -l 3 --sort-by likes --with-comments-replies -o <custom>` | exit 0, `--out` tratado como pasta base |
| `comments --url https://example.com/x` | **exit 2**, mensagem clara |
| `search -l 0` / `search` sem `-k` | **exit 2** (validação Typer) |
| `profile -u '!!bad'` | **exit 1** depois de chamar a rede (`usuário @!!bad não encontrado`). Cria o diretório `exports/__bad-<hash>/<run>/` **vazio**. Divergência com o README (ver problema 1) |
| `KWAI_MAX_RETRIES=abc` | exit 1 com erro de validação do pydantic. Aceitável |

Não houve falha externa de Kwai durante os testes. Os 200 resultados da busca e a paginação funcionaram. Não consegui provocar 429 ou 5xx reais, então o retry foi avaliado só por leitura de código e pelos testes unitários.

### Validação do schema

Rodei `val5.py` (no scratchpad) sobre todos os JSON gerados e sobre `samples/`:

- `Postagem`: `url`, `engajamento` com as 4 chaves e `coletado_em` presentes em todos.
- `Comentario`: `postagem_url`, `texto` e `coletado_em` presentes em todos.
- Zero ids duplicados em todos os arquivos. Datas em ISO-8601 com `Z`.
- Os 3 `samples/` (5 itens cada) passam.

**Saída em `exports/<dono>/<execução>/posts.json`** (e `comments/<id>.json`). O enunciado diz apenas que a saída deve ser JSON, então a pasta é aceitável. Cada execução ganha pasta própria com timestamp e uuid. Isso evita sobrescrever, mas é mais complexo do que um arquivo único e dificulta achar o resultado. Mitiga o fato de o CLI imprimir `Export directory:`. Os comentários ficam em arquivos separados por post, não em um único arquivo. O `-o` é pasta-base e não arquivo, uma convenção menos intuitiva.

## (c) Critérios

| Critério | Peso | Nota | Justificativa |
|---|---|---|---|
| Corretude das 3 funcionalidades | 30% | 3 | Busca, perfil e comentários funcionam ao vivo. Paginação até 200 itens, dedup verificada, schema válido, ordenação `--sort-by` e múltiplas keywords funcionam. Pontos que seguram o 4: (1) o handle inválido não é rejeitado antes da rede, apesar do README dizer exit 2 (`identifiers.py:22-34`); (2) multi-keyword só consulta a segunda palavra se a primeira não encher o limite, o que surpreende mas está documentado; (3) o coletor depende de engenharia reversa da API móvel (sal fixo, `vid/egid` de um dispositivo fictício), então qualquer mudança de versão do app quebra, e a conformidade com os termos de uso é questionável; (4) `mapping.py` descarta feeds sem `photo_id/handle` com WARNING, e isso é aceitável. |
| Qualidade de código | 25% | 3 | Pontos positivos: mypy strict limpo, ruff com `ANN`/`D`/`B`/`SIM`/`N`/`UP` limpo, docstrings Google, nomes claros, funções curtas, entidades `frozen` e `kw_only`, `StrEnum`, `assert_never`. Descontos: over-engineering evidente para o Nível 1 (ver abaixo), duplicação conceitual entre portas e adapters, `mypy tests` com 8 erros (README só manda checar `src`), logger `httpx` em INFO imprime a URL inteira, com o fingerprint do dispositivo, em cada requisição. |
| Robustez | 20% | 4 | Acima do esperado: rate limiter thread-safe configurável (`ratelimit.py`), retry com `tenacity` e backoff exponencial só para falhas transitórias (429/5xx/transporte/corpo não-JSON, `http_utils.py:9,124`), fallback entre 3 gateways, detecção de laço de cursor (`RepeatedCursorError`), dedup por `id` ou `url`, resultado parcial gravado em `.partial.json` com exit 1, escrita atômica (tmp + rename), nomes seguros para Windows, `Settings` tipada com validação (`ge=0`, `gt=0`), logging com níveis e `-v`. Não vi `Retry-After` nem jitter. |
| Testes | 15% | 4 | 302 testes, 99% de cobertura, sem rede (`respx`, backoff neutralizado). Cobrem domínio, casos de uso, CLI (exit codes), exportação, fixtures sanitizadas de capturas reais, o vetor de assinatura e as amostras. Rodam em ~7 s. Descontei só os erros de mypy nos testes, que não bloqueiam. |
| Documentação e tooling | 10% | 3 | `poetry.lock` commitado, pyproject com ruff/mypy/pytest, `.env.example` e README com instalação e execução que funcionaram na primeira tentativa. PR bem descrita (problema, solução, camadas, checklist). Mas o README é muito longo, e `docs/` tem 32 arquivos / ~3.000 linhas (ADRs, flows, use-cases, business-rules, research) para um desafio de Nível 1. Isso dilui o que importa e há redundância entre arquivos. O README sobre "exit 2 para usuário inválido" não bate com o comportamento real. |

**Bônus (até +10): +5.**

- Cobertura 99%: +3.
- Validação de schema automatizada: +2 (`tests/unit/test_samples.py` instancia as entidades com as amostras, mas só valida estrutura. Não há validação de tipos ou obrigatórios com pydantic nas saídas).
- CI local: ausente (sem Makefile, tox ou pre-commit), então 0.

**Sobre o over-engineering** (evidência):

- 4 portas de entrada ABC (`application/ports/use_case_ports.py:14-43`), cada uma com **uma única implementação**. Servem para o CLI "não conhecer" o caso de uso, mas o CLI de qualquer jeito importa o container.
- 4 portas de saída (`ISearchApiPort`, `IProfileApiPort`, `ICommentApiPort`, `IClockPort`) e `IClockPort` + `SystemClock` só para chamar `datetime.now()`.
- Value objects (`Handle`, `UserId`, `PhotoId`, `CommentId`, `Cursor`, `IsoTimestamp`, `PostReference`) com `__post_init__`, 4 pacotes `__init__.py` quase vazios (`domain/enums`, `domain/entities` e outros), DTOs de comando com `create()` e `__post_init__`.
- Container de composição com `Closeable` Protocol e `Services` com `ExitStack`, para dois clientes HTTP.
- O enunciado do Nível 1 pede módulos separados, não camadas. O próprio projeto reconhece que isso é escopo do Nível 2.

Por outro lado, o DDD não está quebrado. As camadas respeitam a direção das dependências, os use cases são testáveis com fakes e isso explica a cobertura de 99%. É uma escolha consciente e documentada (ADRs), mas desproporcional. Pela regra "complexidade sem propósito conta contra", penalizei apenas Qualidade de código e Documentação. Não penalizei Corretude nem Robustez, que se beneficiam da estrutura.

## (d) Pontos fortes

1. Funciona ao vivo nas 3 funcionalidades, com paginação real validada até 200 itens de busca e 70 posts de perfil, sem duplicatas.
2. Tooling exemplar: mypy strict, ruff com regras amplas incluindo docstrings, 99% de cobertura, testes offline.
3. Tratamento sério de falhas: parcial persistido, escrita atômica, cursor repetido detectado, erros de negócio com `result != 1` diferenciados de erro HTTP.
4. Honestidade técnica: README e `docs/maintenance/research.md` distinguem observação de hipótese, e as limitações conhecidas estão explícitas (ex.: 59 respostas declaradas vs 52 entregues).
5. Config tipada e validada, `.env.example`, sem segredo, `.env` ignorado.
6. Códigos de saída coerentes (0/1/2) e `--help` claro. `--limit` com `min=1`.
7. A PR #4 do mesmo autor (versão enxuta: ~685 linhas de código, 8 módulos e 294 linhas de teste) mostra que ele sabe fazer a versão proporcional. Esta é a versão deliberadamente maximalista.

## (e) Problemas no código

1. **Handle inválido não vira exit 2 e deixa pasta vazia.** `domain/value_objects/identifiers.py:22-34`: `Handle.parse` só rejeita vazio, `@`, `/` e espaços. `'!!bad'` passa, vai à rede e sai com exit 1. Em `entrypoints/cli/export_commands.py:106-107`, `create_export_directory` roda **antes** da coleta, então fica `exports/__bad-<hash>/<run>/` vazio. O README diz que sem nada coletado não cria saída. Sugestão: validar o handle com regex (`^[A-Za-z0-9._-]+$`) e criar a pasta de execução de forma preguiçosa, no primeiro `write_export`.
2. **Logs de `httpx` em INFO imprimem a URL completa**, com `vid`, `egid` e `did` do dispositivo falso (visto na execução de `profile`). Polui a saída e vaza o fingerprint do app emulado. Sugestão: `logging.getLogger("httpx").setLevel(logging.WARNING)` em `shared/logging/logging_config.py:18-23`.
3. **Sem `Retry-After` nem jitter** em `infrastructure/kwai/http_utils.py:124` (`wait_exponential(multiplier=0.5, max=8)`). Com 429 real, o teto de 8 s pode ser insuficiente. Sugestão: ler `Retry-After` e acrescentar `wait_random`.
4. **Dependência de engenharia reversa**: `infrastructure/kwai/mobile/app_identity.py:17` (`SIG_SALT`) e `client.py:33-39` (gateways `kwai-pro.com`). O README admite que o sal só foi provado para uma versão do app. Sugestão: deixar explícito no README, na seção de limitações e na ética, que há risco de quebra e de violação de termos de uso, e oferecer um comando `smoke` para detectar a quebra.
5. **Overfetch na busca** (`application/use_cases/search_posts.py:65`): `limit=command.limit` gera páginas de até 50, então um `-l 80` buscou 100 itens (custo de rede e rate limit a mais). É um desperdício pequeno, mas dá para limitar o tamanho da última página.
6. **Multi-keyword com limite pequeno ignora palavras seguintes** (`search_posts.py:263-279`). Está documentado, mas `-k a -k b -l 12` entrega só `a`. Sugestão: dividir o limite ou avisar com `logger.warning` quando keywords são puladas.
7. **Portas de entrada de uma única implementação** (`application/ports/use_case_ports.py:14-43`) e `IClockPort`. Remover ou justificar. Pelo princípio de não introduzir abstração sem necessidade, bastaria o `Services` do container com os casos de uso concretos.
8. **`mypy tests` com 8 erros** em `tests/unit/test_usecases.py:153,236,258,278,336,337,359`. Tipar o dicionário de `FakeApi` ou rodar `mypy src tests` no README.
9. **Saída não é aderente a um arquivo único.** Pastas por execução (`export_files.py:44-60`) e `.partial.json`. Para avaliadores e pipelines, um `--output arquivo.json` opcional seria mais simples.
10. **Entidades são dataclasses sem validação de contrato.** `domain/entities/post.py:~63` aceita `url=""`, e a obrigatoriedade de `url/engajamento/coletado_em` só é garantida pelo mapeamento. O nível pede "modelos validando o contrato". Pydantic ou um `__post_init__` mínimo cobriria.

## (f) Melhorias de documentação

- Reduzir o README: colocar instalação, 3 comandos de exemplo, testes/lint e links. Mover a seção de arquitetura, as decisões de engenharia sobre assinatura e as limitações para `docs/`. Hoje o README mistura uso e pesquisa.
- Consolidar `docs/` (32 arquivos) em 3 ou 4: uso, arquitetura/decisões, protocolo (assinatura + API móvel) e manutenção. `flows/`, `use-cases/` e `business-rules/` repetem o que o código e as docstrings já dizem.
- Corrigir a promessa do README sobre exit 2 para usuário inválido e sobre não criar saída sem coleta (problema 1).
- Incluir `mypy tests` ou deixar claro que os testes ficam fora da checagem.
- Avisar no README que a coleta de perfil e comentários usa API móvel não oficial assinada e pode quebrar.
- Na PR, linkar para um resumo de 5 linhas de "como validar" (`poetry install`, `pytest`, `ruff`, `mypy`, um exemplo de comando). O PR atual é bom, mas longo.

## (g) Nota base final

Cálculo: soma(peso × nota / 4)

- Corretude: 30 × 3/4 = 22,50
- Qualidade: 25 × 3/4 = 18,75
- Robustez: 20 × 4/4 = 20,00
- Testes: 15 × 4/4 = 15,00
- Documentação: 10 × 3/4 = 7,50

Subtotal = **83,75**. Bônus = **+5**.

**Nota final = 88,75 / 100** (base 83,75 + bônus 5).

Sem eliminatórias: nenhum segredo commitado, o nível foi cumprido e o código roda.

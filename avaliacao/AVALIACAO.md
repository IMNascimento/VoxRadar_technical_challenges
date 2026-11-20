# Avaliação · Desafio Kwai · Nível 1 · teusdev7

**PR:** #3 · **Branch:** `solution/kwai-nivel1-teusdev7` · **Data:** 2026-11-20

| | |
|---|---|
| Nota base (critérios ponderados + bônus) | **70.75** |
| Penalização por uso de IA (−25% da nota base) | **−17.69** |
| **Nota final** | **53.06 / 100** |

## Como a nota foi calculada
Método do `docs/avaliacao.md`: cada critério recebe nota 0–4 e a nota final é a soma de (peso × nota/4), mais o bônus. O nível escolhido é o contrato: avaliamos contra os requisitos do Nível 1. Foco da avaliação: solução, código escrito e README de instalação e execução.

## Penalização
Foi identificado no código entregue o identificador de rastreio do template, inserido de forma mecânica em docstrings, constantes e arquivos de configuração. Isso é indicativo de geração do código por assistente de IA. Conforme a regra da avaliação, aplicamos **−25% sobre a nota base**: 70.75 − 17.69 = **53.06**. A penalização não reflete a qualidade técnica descrita abaixo, que foi avaliada à parte.

---


## (a) Resumo
CLI `kwai-collector` (argparse + httpx + pydantic) com quatro comandos: `buscar`, `perfil`, `comentarios` e `coletar` (extra). As três funcionalidades **funcionaram contra o Kwai real**. O perfil `parkourcity` retornou 7.391 posts únicos. Os comentários de um post dele foram coletados com paginação completa (1.498 únicos). A busca devolveu 49 posts.

A parte de comentários usa um assinador local (`sig`/`__NS_sig3`) reimplementado a partir do APK do Kwai Lite 10.3.20. Ele inclui um blob de 151 KB de material criptográfico. Isso funciona, mas é frágil e arriscado do ponto de vista de ToS.

Ferramentas limpas: `pytest` 235 passed, `ruff` ok, `mypy` ok, tudo offline. A engenharia é sólida no papel, mas o código tem **excesso de arquitetura**. São 9.619 linhas em `kwai_collector/`, com cerca de 1.400 linhas de módulos mortos (`real_comment_client`, `mobile_http_comment_client`, `mock_comment_client`, `adb_comment_provider`, `callback_signature_provider`). Há injeção de dependência por dataclasses de callables em vários `cli_*.py`. A busca tem teto fixo de 5 páginas.

Sem segredo commitado.

## (b) Evidência de execução
Ambiente: Poetry 2.4.3, venv em `(ambiente de avaliação)`, Python 3.12.

| Comando / verificação | Resultado |
|---|---|
| `poetry install` (README) | OK, sem passos faltando. O README manda `cd kwai-project` (placeholder do nome da pasta) e `git clone <URL>`. `poetry check`: All set. |
| `poetry run kwai-collector --help` | OK, lista os comandos. `<cmd> --help` funciona. |
| `poetry run pytest tests -q` | **235 passed** em ~22 s |
| Cobertura (`pytest-cov` instalado à parte, não está no projeto) | **68%** (3137 stmts, 991 miss) |
| `ruff check kwai_collector tests` | All checks passed |
| `ruff format --check` | 95 files already formatted |
| `mypy kwai_collector` | Success: no issues found in 59 source files |
| pytest com sockets bloqueados (plugin `socket.connect` -> erro) | 235 passed, **independente de rede** |
| `grep print(` em `kwai_collector` | nenhum. Uso de `logging`. |
| `buscar parkour --delay 1` | 49 posts únicos em 9 s. Exit 0. Campos obrigatórios presentes. |
| `perfil parkourcity --delay 1` | **7.391 posts únicos** em 10m56s, exit 0. Terminou com "Paginação encerrada porque um cursor foi repetido". Nenhum campo obrigatório nulo. 0 ids duplicados. |
| `comentarios https://www.kwai.com/@parkourcity/video/5200681774517762268 --max-comments 50 --request-interval 1` | 50 comentários em 4 s (páginas 20+20+10). Exit 0. |
| mesmo post, `--max-comments todos --request-interval 0.5` | **1.498 comentários principais únicos** em 52 s (o post declara 1.969 no campo `comentarios`, que provavelmente inclui respostas). |
| Validação de argumentos | `buscar` sem arg: exit 2. `buscar ''`: exit 1. `--max-comments -3` e `abc`: exit 2 com mensagem. `--delay -1`: exit 2. Códigos coerentes. |
| Schema (`docs/schemas.md`) | Postagem e Comentario com todos os campos obrigatórios. Engajamento sem nulos. `data_publicacao` vem **sem fuso** (`2022-12-22T10:53:43`), enquanto `coletado_em` e `data` de comentário vêm com `Z`. |
| `samples/*.json` | Validados por `tests/test_sample_contracts.py` com os modelos pydantic. Têm só 2 registros cada, curados à mão, não saída real. |

Não houve falha externa nem do código nas execuções reais.

## (c) Notas por critério

| Critério | Peso | Nota | Justificativa |
|---|---|---|---|
| Corretude das 3 funcionalidades | 30% | **3** | As três funcionam com dados reais, em volume (7.391 posts, 1.498 comentários), com dedup e fim de paginação detectado. Descontos: a busca está limitada a 5 páginas (`search_all_posts(max_paginas=5)`, `kwai_client.py:81`) e não é configurável pela CLI, então devolve ~49 resultados. Aceita só uma palavra-chave por execução. `data_publicacao` sai sem fuso. O fim do perfil é inferido por cursor repetido, sem distinguir "fim" de "cursor travado". `coletar` é fixo em 10 posts (`MAX_POSTS`, `cli.py:92`). Os comentários dependem de um assinador de APK específico (v10.3.20.540101), o que é frágil. |
| Qualidade de código | 25% | **2** | Ponto positivo: mypy e ruff limpos, type hints completos, `py.typed`, pydantic. Pontos negativos graves: **over-engineering e código morto** (ver (e)). A estrutura `cli.py` + `cli_builders/collect/commands/comments/normalizers/parsers/utils` com dataclasses de callables (`SearchCommand`, `ProfileCommand`) é DI sem propósito para um CLI de 3 comandos. O dispatch é manual (`_dispatch_command`) em vez de `argparse` subparsers. Há retry duplicado em `kwai_client.py:28-64` e `profile_client.py:51-125`, com semânticas diferentes. `logging.basicConfig` roda no import do módulo (`cli.py:68`). Os modelos pydantic têm tipos frouxos (`url: str`, não `HttpUrl`). Alguns módulos passam de 400 a 760 linhas (`post_detail_client.py` 762, `cli_collect.py` 696, `mobile_http_comment_client.py` 674). |
| Robustez | 20% | **3** | Existe retry com backoff exponencial configurável (`KWAI_MAX_TENTATIVAS`, `KWAI_BACKOFF_BASE`), tratando 429 e 5xx e erros de rede. `RequestRateLimiter` tem `Retry-After` para comentários. Há paginação por cursor com dedup por id, detecção de cursor repetido, checkpoint e `--resume`. A config usa pydantic-settings, e os `--delay` e `--request-interval` são validados (finitos, não negativos). O logging é adequado. Descontos: não há jitter nem `Retry-After` em busca e perfil. Os defaults de `max_tentativas`/`backoff` são amarrados no import (`settings.x` como valor default). O perfil só grava o JSON no fim (11 min de coleta sem salvamento parcial). `httpx.post` é chamado sem timeout explícito em busca e perfil, usando o default de 5 s do httpx. |
| Testes | 15% | **3** | 235 testes, offline (verificado com socket bloqueado), 68% de cobertura. Cobrem parsers, CLI com fakes, paginação, rate limit, checkpoint e contrato dos samples. Descontos: boa parte da suíte (mock signer, ADB, native boundary, ~1/3 dos arquivos) testa módulos que o fluxo principal nem usa. Não há teste de retry/backoff em busca e perfil via `httpx.MockTransport` visível no `test_kwai_client`. Cobertura de 68% sem meta nem relatório configurados no `pyproject`. |
| Documentação e tooling | 10% | **3** | Poetry com `poetry.lock`, `pyproject` com ruff e mypy declarados, README com instalação e verificações, `docs/USAGE.md` detalhado, `COLETA_COMENTARIOS.md` técnico e PR bem descrita (abordagem HTTP, trade-offs, limites honestos, como rodar). Pontos negativos: o README da raiz mistura a seção do candidato com o enunciado do template. O USAGE manda `cd kwai-project` (nome que não existe). O PR reconhece dependência de uma versão do APK. O `docs/validations/*.json` mostra dados de 09/10 e não é reproduzível pelo avaliador. |

**Bônus: +2.** Validação de schema automatizada dos samples com pydantic (`test_sample_contracts.py`) e testes de contrato. Não há cobertura alta (68%) nem CI local (Makefile, pre-commit ou workflow).

## (d) Pontos fortes
- Funciona de ponta a ponta no Kwai real, sem `.env` nem credenciais. O perfil com 7,4 mil posts e os 1,5 mil comentários paginados são resultado de volume real.
- Ferramentas verdes: ruff, ruff format, mypy e pytest, tudo reproduzível com `poetry install`.
- Testes totalmente offline, 235 casos.
- CLI com validação de argumentos e exit codes coerentes (0, 1, 2). `--help` por subcomando.
- Honestidade técnica no PR e no USAGE (limites de cursor, dependência de versão do app, "não comprova esgotamento do histórico").
- Checkpoint e `--resume` para coletas longas de comentários; rate limiter com `Retry-After`.
- Config tipada com pydantic-settings e `ge=0`.

## (e) Problemas no código e sugestões

1. **Código morto, ~1.400 linhas.** Sem nenhum import em `kwai_collector/`: `clients/real_comment_client.py` (234), `clients/mobile_http_comment_client.py` (674), `clients/mock_comment_client.py` (87), `providers/adb_comment_provider.py` (248) e `security/callback_signature_provider.py` (152). Alguns ainda têm testes (mock, ADB). Remover, junto com os testes, ou justificar no README. Mock/ADB/live/mobile são clientes alternativos não usados pelo CLI.
2. **Over-engineering na CLI.** `cli.py` (368) mais `cli_builders`, `cli_collect` (696), `cli_commands`, `cli_comments` (367), `cli_normalizers`, `cli_parsers` e `cli_utils`. Dataclasses com `Callable` injetados (`cli_commands.py:15-70`, `cli.py:155-200`) não trazem testabilidade que `monkeypatch` ou parâmetros simples não dessem. Sugestão: pacote `cli/` com `argparse` subparsers e funções diretas. A colocação `kwai_collector/cli_*.py` na raiz do pacote polui a estrutura.
3. **Retry duplicado e inconsistente.** `clients/kwai_client.py:28-64` usa um loop com `isinstance`, e `clients/profile_client.py:51-125` outro, com contagem diferente de tentativas (0-based vs 1-based) e `_calcular_backoff` separado. Extrair um `request_with_retry()` único (com jitter e `Retry-After`) e reaproveitar o `RequestRateLimiter`.
4. **Busca limitada.** `kwai_client.py:81` `max_paginas=5` fixo e sem flag na CLI, devolvendo ~49 posts. O `README`/`USAGE` não avisa. Sugestão: `--max-pages` ou paginar até cursor vazio, como o perfil.
5. **Defaults amarrados no import.** `kwai_client.py:16-18`, `profile_client.py:~44`, `cli_parsers.py` usam `settings.max_tentativas` como valor default em assinatura (`max_tentativas: int = settings.max_tentativas`). Alterar a env depois do import não surte efeito, e `get_all_profile_posts` nem repassa `max_tentativas` a `get_profile_page` (`profile_client.py:~160`). Passar `Settings` explicitamente.
6. **Efeito colateral no import.** `cli.py:68` `logging.basicConfig(level=INFO, ...)` e `config.py` `settings = Settings()` no nível do módulo. Mover para `main()` e criar settings sob demanda.
7. **Sem timeout explícito** em `httpx.post` de busca e perfil (`kwai_client.py:~43`, `profile_client.py:~65`) e sem `httpx.Client` reaproveitado (nova conexão por página; 11 min para 370 páginas).
8. **Sem salvamento incremental no perfil.** `ProfileCommand.execute` (`cli_commands.py:~170-215`) só grava ao final. Uma falha em 10 min perde tudo. O comando de comentários já tem checkpoint; replicar.
9. **Datas inconsistentes.** `parsers/post_parser.py:24-30` usa `strptime(...)` + `noqa: DTZ007` e deixa `data_publicacao` sem fuso, enquanto `coletado_em` leva UTC. Definir o fuso (provavelmente UTC) ou documentar no PR/README.
10. **Modelos frouxos.** `models/postagem.py`: `url: str` sem validação de URL, `autor` obrigatório mesmo quando ausente, sem `ConfigDict(extra=...)`. A saída é um `dict` e não `model_dump(mode="json")` em todo o caminho (`normalizar_posts_com_parser`). Usar `HttpUrl` e serializar via modelo.
11. **Material criptográfico e ToS.** `security/kwai_lite_103_sig3_material.bin` (151 KB) mais `kwai_lite_103_offline_sig3_signer.py` reimplementam a assinatura anti-bot do app móvel e usam `User-Agent` de Android/Chrome (`mobile_http_comment_client.py:~48`). Funciona, mas é engenharia reversa de proteção da plataforma, que pode violar ToS e quebrar a qualquer atualização. O PR reconhece a dependência de versão, mas não discute o aspecto legal. Documentar o risco e oferecer fallback (por exemplo, o endpoint "tiny" já usado para até 20 comentários).
12. **Dispatch frágil.** `cli.py` `_dispatch_command`: qualquer primeiro argumento desconhecido cai em `_main_coletar(argumentos)`, de modo que um erro de digitação (`kwai-collector buscr x`) vira "coletar do perfil buscr". Usar `argparse` subparsers e exigir comando.
13. **Docstrings vazias.** Muitos módulos têm `"""A1_Radar."""`, e `config.py` define `A1_Radar = "A1_Radar"`; 59 arquivos em `kwai_collector/` e `tests/` (inclusive `.env.example`) levam esse marcador. É só observação. Docstrings que não descrevem o módulo e constantes sem uso não ajudam o leitor (sem impacto na nota).
14. **Saída padrão em `samples/`.** `cli_parsers.py:16` `DEFAULT_OUTPUT_DIR = Path("samples")`. Rodar a CLI sobrescreve ou suja a pasta de samples do repositório. Usar `./output`.

## (f) Melhorias de documentação
- Corrigir `cd kwai-project` no `docs/USAGE.md` (nome da pasta do repo) e deixar a instalação autocontida no README.
- Separar, no README da raiz, a seção do candidato do enunciado do template (hoje a seção de solução é prefixada ao índice do desafio).
- Documentar o limite de 5 páginas da busca, os 10 posts de `coletar`, e o que `todos` realmente garante. Citar o formato de `data_publicacao` (sem fuso).
- Incluir seção de decisões e trade-offs (por que assinador local, por que não browser) e riscos legais e de fragilidade, além da lista de módulos não usados (ou removê-los).
- Dizer como medir cobertura (`pytest-cov` no dev group) e como regerar `docs/validations`.
- Samples com 2 registros: gerar um sample real maior (ex.: 10 itens) a partir da CLI.

## (g) Nota final

| Critério | Peso | Nota | Contribuição |
|---|---|---|---|
| Corretude | 30 | 3 | 22,50 |
| Qualidade | 25 | 2 | 12,50 |
| Robustez | 20 | 3 | 15,00 |
| Testes | 15 | 3 | 11,25 |
| Docs/tooling | 10 | 3 | 7,50 |
| **Nota base** | | | **68,75 / 100** |
| Bônus | | | +2 |
| **Total** | | | **70,75** |

Eliminatórios: nenhum segredo commitado (varredura por tokens/cookies/bearer sem achados; `.env.example` só tem delays e tentativas).

---

## Escalabilidade
A análise de escalabilidade desta solução (coleta em larga escala, gargalos, medições e roadmap) está em [ESCALABILIDADE.md](ESCALABILIDADE.md).

## Não concordou com a nota?
Se você não concorda com a sua nota, chame **IMNascimento**: [github.com/IMNascimento](https://github.com/IMNascimento).

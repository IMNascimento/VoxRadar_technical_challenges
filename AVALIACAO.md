# Avaliação · Desafio Kwai · Nível 1 · Lucas7721

**PR:** #4 · **Branch:** `solution/kwai-nivel1-lucas7721` · **Data:** 2026-11-20

| | |
|---|---|
| Nota base (critérios ponderados + bônus) | **86.50** |
| Penalização por uso de IA (−25% da nota base) | não se aplica |
| **Nota final** | **86.50 / 100** |

## Como a nota foi calculada
Método do `docs/avaliacao.md`: cada critério recebe nota 0–4 e a nota final é a soma de (peso × nota/4), mais o bônus. O nível escolhido é o contrato: avaliamos contra os requisitos do Nível 1. Foco da avaliação: solução, código escrito e README de instalação e execução.

---


## (a) Resumo
Pacote `kwai_collector` com CLI Typer (`search`, `profile`, `comments [--with-replies]`), HTTP puro (httpx), sem navegador. Busca usa o endpoint JSON web. Perfil e comentários usam a API móvel anônima do Kwai Lite, com `sig` MD5 reproduzido em Python e validado por teste contra um request real. Instala e roda como o README manda, as 3 funcionalidades funcionam contra o Kwai real, e lint/tipos/testes passam limpos. É uma entrega forte para o Nível 1. Os pontos fracos são: singleton de config no import, erro de config/`ValidationError` virando traceback, modo "tudo ou nada" e documentação muito acima do necessário (25 arquivos em `docs/`). A dependência de um sal de app extraído por engenharia reversa é frágil e merece nota de risco.

## (b) Evidência de execução
Ambiente: venv isolado em `scratchpad/venvs/pr4` (Python 3.12.3, Poetry do sistema). Usei `POETRY_VIRTUALENVS_IN_PROJECT=false` porque o `poetry.toml` do candidato força `in-project = true`. Checkout não modificado (`git status` limpo; removi o `.coverage` que eu gerei).

| Passo | Resultado |
|---|---|
| `poetry install` | OK, sem falhas. `poetry check` só emite warnings de depreciação (`[tool.poetry.authors]` e `scripts`). |
| `poetry run pytest` | **22 passed**, 0.58s, 2 warnings de depreciação do click/typer. Sem rede (respx). |
| Cobertura (`coverage`) | **93%** (cli 93, client 92, parser 95, scraper 92, models/config 100, `__main__` 0). |
| `ruff check .` | All checks passed. |
| `ruff format --check .` | 14 files already formatted. |
| `mypy` (strict + plugin pydantic) | Success: no issues in 8 source files. |
| `kwai-collector --help` | OK (3 comandos). `no_args_is_help=True`. |

Execução real contra o Kwai (rede liberada):

- `profile --user parkourcity --limit 3 --out usuario.json`: 3 itens em 2.5s, rc=0.
- `search -k sports -k parkour -l 20`: 20 itens em 1.9s. Só consultou "sports", porque o limite já foi atingido; as palavras são consultadas em sequência, não intercaladas.
- `search -k parkour -l 120`: 120 posts, 120 ids únicos. A paginação passou de 50 e a dedup funcionou. Houve um WARNING "post ignorado: veio sem photo_id ou usuário".
- `profile -u parkourcity -l 70`: 70 posts, 70 únicos (3 páginas de 30).
- `comments --url .../@parkourcity/video/5240651225143682227 -l 50`: 15 comentários (o post só tem 15). `--with-replies` também deu 15, com `parent_id` nulo em todos. Esse post não tem respostas, então o caminho de respostas **não foi exercitado ao vivo**; ele só é coberto pela fixture `mobile_replies.json`.
- Validação: os 3 JSONs reais e os 3 `samples/` carregam nos modelos Pydantic (`Post`/`Comment`). Os campos batem com `docs/schemas.md`: `id,url,autor{usuario,id,url_perfil},texto,data_publicacao,engajamento{4},coletado_em` e `id,postagem_url,autor,texto,curtidas,data,coletado_em`. Datas em ISO-8601 UTC com `Z`. Métricas ausentes viram `null`. Com `--with-replies` há campos extras (`parent_id` etc.), permitidos pelo schema.

Casos de erro:

| Caso | Resultado |
|---|---|
| URL inválida (`example.com/x`) | rc=2, mensagem clara |
| `--user ""` | rc=2 |
| Usuário inexistente | rc=1, "usuário @... não encontrado" |
| Keyword vazia | rc=2 |
| `--limit abc` / `--limit 0` | rc=2 (validação Typer) |
| `--url https://example.com/video/123` | **aceito** (rc=0, `[]`): só o regex `/video/\d+` é validado, sem checar o domínio |
| `KWAI_MAX_RETRIES=abc` | **traceback bruto** do pydantic, rc=1, na importação do módulo |

Não houve falha externa durante a execução. Segredos: nenhum `.env` commitado. O `SIG_SALT`, `CLIENT_KEY` e os identificadores de dispositivo em `client.py` são constantes públicas do app Kwai Lite obtidas por captura (não são credenciais do candidato). Não é eliminatório, mas veja o risco de ToS em (e).

## (c) Notas por critério

| Critério | Peso | Nota | Justificativa |
|---|---|---|---|
| Corretude das 3 funcionalidades | 30% | 4 | As três funcionam ao vivo, com paginação real (>50 na busca, 3 páginas no perfil), dedup e limites coerentes. Saída aderente ao schema. Engenharia reversa do `sig` com teste de vetor real. Ressalvas menores: respostas não validadas ao vivo, domínio da URL não checado, multi-keyword sequencial. |
| Qualidade de código | 25% | 3 | mypy strict e ruff limpos, módulos bem separados, nomes claros, sem `print`, sem funções gigantes. Falta: `settings` como singleton criado no import (`config.py:19`), estado global `_last_request` (`client.py:~67`), datas como `str` com regex em vez de `datetime`, ruff com só `E,F,I,UP` (sem `B`, `SIM`, `ANN`), quase sem docstrings (comentários no lugar), modelos com nomes em inglês (`Post`/`Comment`) para um contrato `Postagem`/`Comentario`. |
| Robustez | 20% | 3 | Rate limit configurável, retry com backoff exponencial limitado (0.5·2^n, máx. 8s), troca de host, checagem de `result != 1`, proteção contra cursor repetido, dedup, logging em stderr, config tipada. Falta: jitter e `Retry-After` no 429, tratamento de `ValidationError` e de `Settings` inválido (traceback, o próprio PR admite o primeiro), e o modo tudo-ou-nada perde minutos de coleta em falha tardia (admitido no README). |
| Testes | 15% | 3 | 22 testes, 93% de cobertura, 100% offline (respx, fixtures reais recortadas, sleep/delay zerados). Cobrem sig, retry, 4xx, troca de host, erro de negócio, códigos de saída, paginação da busca e samples contra o schema. Faltam: teste de dedup entre múltiplas keywords, de cursor repetido, de `--limit` em perfil/comentários, e de `ValidationError`. |
| Documentação e tooling | 10% | 3 | README correto e completo (instalação, comandos, saída, códigos de saída, decisões, limitações honestas), Poetry + lock, `.env.example`, PR bem descrito com checklist. Descontado por over-engineering documental (25 arquivos `.md`, ADRs, casos de uso e fluxos para uma CLI de 3 comandos), pela remoção dos arquivos do enunciado/template no PR e pelo `poetry.toml` que força venv no projeto. |

Soma ponderada: 30·4/4 + 25·3/4 + 20·3/4 + 15·3/4 + 10·3/4 = 30 + 18,75 + 15 + 11,25 + 7,5 = **82,5**

Bônus (até +10):

- Cobertura alta (93%): +2
- Validação de schema automatizada (`test_samples.py` + modelos Pydantic com regex de data): +2
- CI local / Makefile / pre-commit: ausente, 0

Total de bônus: **+4**

## (d) Pontos fortes
- Solução realmente funcional ao vivo nos 3 casos, sem browser, em ~1–3s por coleta.
- `create_signature` validado contra um `sig` real capturado do app (`tests/test_client.py:32`).
- Tratamento correto de HTTP 200 com `result != 1` (`client.check_result`), 4xx sem retry, e fallback entre 3 hosts.
- Proteção de paginação em camadas: cursores de fim, cursor repetido, página vazia, página sem item novo (busca).
- Contrato honesto: `null` quando a API não informa, nunca `0` inventado (`parser.to_int`).
- Logs vão para stderr e JSON para stdout, o que permite pipe limpo. `--verbose` e códigos de saída 0/1/2 documentados e testados.
- README com limitações honestas (fim de cursor não prova completude, versão do app, tudo-ou-nada), em linha com "honestidade técnica".
- Fixtures reais recortadas e documentadas.

## (e) Problemas no código (arquivo:linha) e sugestões
1. `kwai_collector/config.py:19`: `settings = Settings()` no import. Um env inválido (`KWAI_MAX_RETRIES=abc`) derruba a CLI com traceback antes do Typer. Sugestão: `get_settings()` com `lru_cache`, chamado dentro dos comandos, com captura de `ValidationError` -> exit 2. Isso também elimina o monkeypatch no singleton em `tests/conftest.py`.
2. `kwai_collector/cli.py` (`collect_and_save`, ~l.30-37): só captura `InvalidInput` e `KwaiError`. `pydantic.ValidationError` (modelos construídos em `parser.py`) escapa como traceback, e o PR admite isso. Sugestão: capturar e sair com 1 e mensagem; ou ignorar o item inválido com `log.warning` como já se faz para post sem id.
3. `kwai_collector/scraper.py:134` (`get_photo_id`): regex `/(?:video|photo)/(\d+)` aceita qualquer domínio (`https://example.com/video/123` -> consulta o post 123). Sugestão: validar host `kwai.com`/`www.kwai.com` com `urllib.parse`.
4. `kwai_collector/client.py:~67-75` (`_last_request` global e `wait_delay`): estado de módulo, não thread-safe, difícil de isolar. Sugestão: classe `KwaiClient` com `httpx.Client` reutilizável (conexões persistentes, mesmo header) e o rate limiter como atributo.
5. `kwai_collector/client.py:~101-103` (`post_json`): `httpx.post` cria nova conexão a cada chamada. Sugestão: `httpx.Client` com `timeout` e headers.
6. `kwai_collector/client.py:~132` (`with_retry`): backoff sem jitter e sem respeitar `Retry-After` em 429; sleeps não-configuráveis (0.5 e 8 fixos, números mágicos). Sugestão: `backoff_base` e `backoff_max` em `Settings`, jitter, `Retry-After`.
7. `kwai_collector/models.py:4` e campos de data: `str` + regex em vez de `datetime`, o que pede `ms_to_iso` manual. Sugestão: `datetime` com `field_serializer` para `...Z`.
8. `kwai_collector/models.py`: nomes `Post`/`Comment` divergem do contrato `Postagem`/`Comentario`; e a saída `--with-replies` mistura dois shapes numa lista (raiz com `respostas_total`, resposta sem). Sugestão: aliases ou renomear; considerar `respostas_total` sempre presente.
9. `kwai_collector/scraper.py:42-79` (`search_posts`): multi-keyword é sequencial e `--limit` é global, então as palavras seguintes podem nunca ser consultadas (comportamento documentado, mas surpreendente). Sugestão: intercalar ou limite por palavra (`--per-keyword`).
10. `kwai_collector/scraper.py:93-130` (`get_user_posts`) e `get_root_comments`: o laço repete a mesma estrutura de paginação (`seen`, `seen_cursors`, `next_cursor`, `limit`) três vezes. Sugestão: gerador genérico `paginate(fetch, parse, key)`; também permitiria saída parcial/stream em vez de tudo-ou-nada.
11. `kwai_collector/scraper.py:130` (`get_user_posts`): quando `limit` é atingido a função faz `return` antes do `log.info` final (logging inconsistente). Menor.
12. `pyproject.toml`: ruff só com `E,F,I,UP`. Sugestão: acrescentar `B`, `SIM`, `RUF`, `ANN` (mypy strict já cobre parte). `poetry.toml` com `in-project=true` altera o ambiente do avaliador; melhor deixar em `.gitignore`/docs.
13. Dependência de sal e identificadores de dispositivo extraídos do app (`client.py:~15-45`): risco de ToS e de quebra silenciosa quando o app atualizar. O README documenta; considerar um teste de fumaça opt-in (`pytest -m live`) que detecte a quebra.

## (f) Melhorias de documentação
- Reduzir `docs/` para README + `docs/architecture.md` + 1 arquivo de decisões. As pastas `adr/`, `use-cases/`, `flows/`, `business-rules/` e `maintenance/` repetem o README e a descrição da PR; mais superfície para ficar desatualizada. Sem benefício proporcional num Nível 1.
- O README tem tabela de índice com 13 links; um leitor que só quer instalar e rodar precisa de 3 seções. Está correto, mas poderia mover "Decisões" e "Limitações" para o fim ou para o PR.
- Dizer explicitamente o que `poetry.toml` faz (venv in-project) e como usar a venv.
- Documentar que `--with-replies` não foi validado ao vivo em post com respostas, ou incluir um post de exemplo que as tenha.
- Marcar no PR que removeu arquivos do template (`niveis/`, `docs/schemas.md`, `avaliacao.md`) e explicar o porquê (nada impede, mas foge do padrão).
- Explicitar o aviso legal/ToS sobre o uso da API móvel não oficial.

## (g) Nota base final
Soma ponderada = 82,5; bônus = +4.
**Nota base: 82,5 / 100. Com bônus: 86,5.**

# Avaliação · Desafio Kwai · Nível 0 · mth65

**PR:** #6 · **Branch:** `solution/kwai-nivel0-matheusreis` · **Data:** 2026-11-20

| | |
|---|---|
| Nota base (critérios ponderados + bônus) | **61.00** |
| Penalização por uso de IA (−25% da nota base) | **−15.25** |
| **Nota final** | **45.75 / 100** |

## Como a nota foi calculada
Método do `docs/avaliacao.md`: cada critério recebe nota 0–4 e a nota final é a soma de (peso × nota/4), mais o bônus. O nível escolhido é o contrato: avaliamos contra os requisitos do Nível 0. Foco da avaliação: solução, código escrito e README de instalação e execução.

## Penalização
Foi identificado no código entregue o identificador de rastreio do template, inserido de forma mecânica em docstrings, constantes e arquivos de configuração. Isso é indicativo de geração do código por assistente de IA. Conforme a regra da avaliação, aplicamos **−25% sobre a nota base**: 61.00 − 15.25 = **45.75**. A penalização não reflete a qualidade técnica descrita abaixo, que foi avaliada à parte.

---


## (a) Resumo
Coletor em arquivo único (`kwai_collector.py`, 367 linhas) com Playwright, que intercepta XHR (busca) e lê `window.__NUXT__` (usuário). **Busca e usuário funcionam contra o Kwai real** e produzem JSON aderente ao schema. **Comentários não funciona**: sempre grava `[]`. O README admite a limitação, mas a explicação não se confirmou na minha execução (ver (b)). Os samples de busca e usuário são reais (os IDs bateram com uma nova execução). O código é legível, mas tem tratamento de erros fraco, um limite prático de ~20–24 itens e README/PR com imprecisões.


## (b) Evidência de execução
Ambiente: venv isolado, Python 3, playwright 1.47.0. Segui o README: `pip install -r requirements.txt`, `playwright install chromium`, `cp .env.example .env`.
- A instalação funcionou sem falhas. Os passos estão completos e corretos.
- O `.env.example` traz `KWAI_HEADLESS=false`, e o README diz que "os valores padrão já funcionam". Rodei com `KWAI_HEADLESS=true`. Em servidor sem display o padrão falharia, e o README não avisa. Em máquina com `DISPLAY`, abre janela.
- O `.env.example` define `KWAI_DEFAULT_LIMIT_*`, `KWAI_OUTPUT_DIR` e `KWAI_LOG_LEVEL`, mas **nenhuma dessas variáveis é lida** no código. O README promete "todos os parâmetros ajustáveis ficam no .env", e isso é só parcialmente verdade.

| Comando | Resultado |
|---|---|
| `usuario --user "@parkourcity" --limit 10` | OK, 10 posts, ~7s, 0 duplicados, ints, datas ISO-Z, `url_perfil` correto |
| `usuario --user parkourcity --limit 60` | Só **20** (só o SSR). O scroll não trouxe mais nada: o laço `while len<limit` é pulado quando o SSR já alcança o limite, e com limit 60 as 4 rolagens não geraram XHR. Isso não é falha de rede: `limit` > 20 é silenciosamente ignorado e nada é avisado. |
| `usuario --user naoexiste_zzz_98765` | Imprime `Erro ao acessar perfil: object of type 'NoneType' has no len()`, grava `[]` e sai com rc=0. A mensagem é críptica (causa: `feeds` é `None`). |
| `usuario --user "@EleicoesBrasil" --limit 3` | Mesmos 3 IDs do `samples/usuario_sample.json`, então o sample é real. |
| `busca --keyword parkour --limit 5` | OK, 5 posts. A página dispara 2 XHR (14+10) = 24 itens, sem paginação. |
| `busca --keyword parkour --limit 100` | Só **24**. |
| `busca --keyword xqzjkwpoiuy123` | Devolve 5 vídeos sem relação com o termo (o Kwai faz fallback). O código não valida relevância. Falha externa/semântica, não do código. |
| `comentarios --url .../@parkourcity/video/5226014520358720568` | `[]` em ~14s, com a mensagem "Nenhum comentário capturado (o Kwai pode exigir sessão autenticada)". |
| `comentarios --url foo` | Imprime "URL inválida." e **não grava arquivo**, com rc=0. |
| `comentarios --url .../video/999` | Também `[]`, indistinguível de um post sem comentários ou bloqueado. |
| `busca --limit abc` | Erro do argparse (ok). |

Sobre o bloqueio dos comentários, fiz uma sonda separada. O XHR `getComments/list` respondeu `{"result":1,"host-name":...}` **sem lista de comentários**, e não `result:11` como o README afirma. `__NUXT__` só continha `comment_count`. O texto do DOM (headless, anônimo) listava vídeos sugeridos, não comentários. Ou seja, o bloqueio anônimo é plausível e é falha externa, mas a evidência do README (`result:11`, "comentários aparecem no DOM") não se reproduziu. O código também não registra nem diferencia "resposta recebida sem comentários" de "endpoint nunca chamado". Em nenhum caso há tentativa de fallback (DOM, outra API ou outro endpoint). A funcionalidade 3 não entrega dados.

Segredos: nenhum commitado. `.env` está no `.gitignore` e o `.env.example` só tem config.

## (c) Critérios

| Critério | Peso | Nota | Justificativa |
|---|---|---|---|
| Corretude das 3 funcionalidades | 45% | 2 | Busca e usuário entregam dados reais corretos, porém limitados (24 e 20 itens) e sem paginação efetiva. Comentários entrega apenas `[]`, falha externa documentada, mas sem fallback. Erros comuns: URL inválida tratada, perfil inexistente com mensagem ruim e rc=0 sempre. |
| Qualidade de código | 25% | 3 | Estrutura clara (helpers, montadores, uma função por modo, CLI), nomes em português coerentes, docstrings, `try/finally` fechando o browser. Descontos: handlers de resposta duplicados, `except Exception: pass`, `print` em vez de `logging`, esperas fixas e números mágicos, variáveis não usadas, config do `.env` parcialmente morta. |
| Aderência aos schemas | 15% | 3 | Campos, tipos, datas ISO-Z e `coletado_em` corretos. Engajamento ausente vira `0` (schema pede `null` quando incerto). A URL de fallback `/explore/<kw>` não é URL de postagem. Comentário só é validável no papel. |
| Documentação (README e PR) | 15% | 2 | README com instalação, uso, decisões técnicas e limitação bem explicados, o que é positivo. Mas há erros: "EXECUCAO.md: este arquivo", `cd kwai`, "busca e usuario operam 100%" (na verdade ~24/~20 itens), headless padrão, variáveis do `.env` inexistentes, afirmações de diagnóstico não reproduzidas. O corpo do PR é de uma linha, com o template (decisões, checklist, limitações) sem preencher. |

Bônus (até +10): **+1**. O scroll para paginação do usuário está escrito (4 tentativas vazias), mas não funcionou na prática. Não há tratamento de rate limit nem testes.

## (d) Pontos fortes
- Abordagem coerente e justificada (interceptar XHR / SSR em vez de reverse de assinaturas).
- Dedupe por ID, normalização de data (s/ms) e `html.unescape` do texto.
- Honestidade sobre a limitação dos comentários, com diagnóstico e trabalho futuro.
- Samples reais e consistentes com a saída atual. `.gitignore` e `.env.example` adequados.
- Instalação reproduzível, com o aviso útil do `playwright install chromium`.

## (e) Problemas no código
- `kwai_collector.py:152-158`: `_extrair_feeds_do_nuxt` não trata `feeds` ausente/`None` (só captura `KeyError/IndexError/TypeError` na leitura). Perfil inexistente cai em `len(None)` na linha 245, e a mensagem final é "NoneType has no len()". Sugestão: `return ... .get("feeds") or []` e avisar "perfil não encontrado".
- `:187-202, 240-275, 314-327`: `except Exception` genérico imprime e continua. Sai com rc=0 e grava `[]` mesmo em erro de rede/timeout. Sugestão: tratar `PlaywrightTimeoutError` separadamente, `sys.exit(1)` em falha e distinguir "sem resultados" de "erro".
- `:182-183, 235-236, 309-310`: `except Exception: pass` engole erros de parse em silêncio. Sugestão: logar em debug.
- `:175-185, 229-238, 302-310`: três handlers de resposta quase idênticos. Sugestão: uma função fábrica `_coletor_xhr(filtro, destino)`.
- `:176`: filtro `"outer" in response.url` é frágil (qualquer URL com "outer"). Use `"/search/word/outer"`.
- `:233-236`: no usuário, captura qualquer XHR com `feeds`, incluindo sugestões/recomendações, e pode misturar posts de outros autores no perfil. Filtre `feed["user_id"]` ou o endpoint de perfil.
- `:190, 242, 318`: esperas fixas de 4000 ms (e `wait_after_load`). O `4000` não é configurável. Sugestão: `page.expect_response(...)` ou `wait_for_load_state`. O `4000`/`range(4)`/`tentativas_vazias < 4`/`3000`/`800` são números mágicos.
- `:255-268`: o laço de scroll é pulado quando o SSR já tem ≥ `limit`, e para `limit` > 20 não trouxe mais itens na prática. Não há aviso de que o limite não foi atingido. Sugestão: imprimir "obtidos X de Y" e verificar o cursor (`pcursor`) do endpoint de paginação.
- `:165-206`: busca não pagina (`pcursor` é retornado e ignorado), então `--limit` > 24 é inútil (README promete padrão 50).
- `:67-74`: `context` retornado e nunca usado. Não usa `with`/context manager para fechar o browser em caso de falha ao abrir contexto.
- `:24-32`: apenas 4 variáveis são lidas. `KWAI_DEFAULT_LIMIT_*`, `KWAI_OUTPUT_DIR` e `KWAI_LOG_LEVEL` do `.env.example` ficam sem efeito, e `--limit` tem default fixo (`:345, 350`). Padrão `KWAI_HEADLESS=false` quebra em servidor.
- `:85, 87, 167, 201...`: uso de `print` em vez de `logging` (o `.env.example` fala em `KWAI_LOG_LEVEL`).
- `:127-130, 146`: engajamento ausente vira `0` e não `null`. Sugestão: `feed.get("like_count")`.
- `:106-111`: URL de fallback `/explore/<kw>` ou a home como URL de postagem não é URL válida de post. Preferir `None`/descartar.
- `:291-293`: URL inválida retorna sem gravar arquivo e sem rc≠0. `"kwai.com" in url` aceita `evil.com/?kwai.com`. Use `urlparse` para validar host e caminho `/video/`.
- `:329-330`: não distingue "bloqueio anônimo" de "post sem comentários". Registrar o `result`/payload do endpoint em log melhoraria o diagnóstico.
- `pyproject.toml`: sobra do template (Poetry, `packages = kwai_collector` que não existe, python ^3.11 vs README 3.10+). Remover ou deixar coerente. `requirements.txt` está ok.

## (f) Melhorias de documentação
- Corrigir "EXECUCAO.md: este arquivo", o `cd kwai` e o link "Especificação do desafio → README.md" (o README do desafio foi sobrescrito).
- Documentar o teto real (~20 usuário / ~24 busca) e que `--limit` maior que isso é ignorado.
- Remover "100%" e o sufixo "A1_Radar" do cabeçalho. Informar que `KWAI_HEADLESS=true` deve ser usado em servidor/CI.
- Alinhar o `.env.example` ao que é de fato lido, ou implementar as variáveis restantes.
- Reconferir/atualizar o diagnóstico de comentários (a resposta observada foi `result:1` sem lista) e mostrar o payload real.
- Preencher o PR com o template: abordagem, decisões, limitações, checklist.

## (g) Nota base
- Corretude: 2/4 × 45% = 22,5
- Qualidade: 3/4 × 25% = 18,75
- Schemas: 3/4 × 15% = 11,25
- Documentação: 2/4 × 15% = 7,5
- **Soma = 60,0** + bônus 1 = **61,0 (nota final), nota base 60,0**

Avaliação feita em 2026-11-20. Artefatos de execução em `(ambiente de avaliação)`. Criei `.env` no checkout (gitignored) ao seguir o README; nenhum arquivo versionado foi alterado e não houve push.

---

## Escalabilidade
A análise de escalabilidade desta solução (coleta em larga escala, gargalos, medições e roadmap) está em [ESCALABILIDADE.md](ESCALABILIDADE.md).

## Não concordou com a nota?
Se você não concorda com a sua nota, chame **IMNascimento**: [github.com/IMNascimento](https://github.com/IMNascimento).

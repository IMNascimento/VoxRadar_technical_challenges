# Análise de escala: PR #6 (mth65), coletor Kwai, Nível 0

Arquivo analisado: `kwai_collector.py` (367 linhas). Referências `L<n>` são linhas desse arquivo.
Medições feitas em 20/11/2026 numa máquina de 16 vCPU e 32 GB, Playwright 1.47 e Chromium headless, rede liberada e sem login.

## 1) Veredito
**Não escala como está.** O custo é de um Chromium novo por chamada, e o teto é de ~24 posts por keyword e ~20 por perfil. Comentários nunca saem, e erros viram `rc=0` com `[]`.
A ideia de interceptar XHR e ler o `__NUXT__` do SSR é reaproveitável. A infraestrutura em volta (browser, persistência, erros, anti-bot) teria de ser reescrita.
Para 10x dá com paralelismo manual e ressalvas. Para 100x é inviável sem proxy e identidade. Para milhões de posts, o teto de itens por consulta impede, qualquer que seja a infra.

## 2) Como funciona hoje
- CLI com três subcomandos (`busca`, `usuario`, `comentarios`, L339-364). Cada execução trata uma keyword, um perfil ou uma URL e termina.
- Cada função abre `sync_playwright()` e chama `_abrir_contexto` (L67-74), que lança **um Chromium novo** e um contexto novo. Fecha tudo no `finally` (L204, L274, L327).
- Busca: navega para `/explore/<kw>` (L188), espera 6 s fixos (L190) e coleta as respostas XHR cuja URL contém `"outer"` (L176). Não pagina.
- Usuário: navega para `/@user`, espera 4 s fixos (L242) e lê `window.__NUXT__...feeds` (L152-158), que traz só a primeira leva (SSR). Depois rola até 4 vezes vazias com 2 s cada (L255-268).
- Comentários: abre a URL, espera 4 s, rola 4x2 s e escuta `getComments/list` (L303). Sem login a lista nunca vem.
- Saída: um JSON por execução, no caminho de `--out`, aberto com `"w"` (L83). Sem fila, sem estado, sem log estruturado.

## 3) Gargalos e bloqueadores

| # | Onde | Problema | Impacto na escala |
|---|---|---|---|
| 1 | L69-74, L172, L226, L299 | Um Chromium por chamada (8 processos, 370-550 MB). Sem reuso de browser nem de contexto. Não há `new_page` em pool. | Custo fixo de ~3-4 s de startup por item. 1000 keywords = 1000 lançamentos de browser. |
| 2 | L190, L242, L316, L257, L320 | Esperas fixas (6 s, 4 s, 4 s, 2 s x N). Nenhuma `expect_response` ou `wait_for_load_state`. | Tempo por execução fica entre 8 e 15 s, mesmo que o dado chegue em 1 s. Rede lenta perde dados em silêncio. Rede rápida desperdiça tempo. |
| 3 | L165-206 | Busca não pagina. O `pcursor` retornado é ignorado e só duas XHR são capturadas (14+10). Em minhas execuções vieram 24 itens. | Teto duro de ~24 posts por keyword. `--limit` maior é ignorado sem aviso. O padrão `--limit 50` (L345) é inalcançável. |
| 4 | L244-268 | Perfil: SSR traz 20 posts. O scroll não gerou XHR nas execuções. O laço é pulado quando o SSR já cobre o limite. | Teto de ~20 posts por perfil. Sem histórico, só os 20 mais recentes. |
| 5 | L176 | Filtro `"outer" in response.url`. L230-234 aceita **qualquer** XHR com `feeds`. | Frágil a mudanças do Kwai. No perfil pode misturar posts recomendados de outros autores sem avisar. |
| 6 | L156 | Dependência de `nuxt["data"][0]["feedsData"]["feeds"]` (caminho profundo do Nuxt). | Qualquer redeploy do front quebra o perfil. Detecção de que quebrou depende de alguém ler os JSONs. |
| 7 | L303-310, L329-330 | Comentários: resposta `getComments/list` sem lista (`result:1`, conforme o relatório prévio). Fim com `[]`. | Zero dados de comentários, sem fallback. Não dá para distinguir bloqueio de post sem comentários. |
| 8 | L200-202, L271-272, L323-325 | `except Exception` imprime a mensagem e segue. Ainda grava `[]`. O processo sai com **rc=0**. L182-183, L235-236, L309-310 têm `except: pass`. | Orquestradores (cron, Airflow, Kubernetes Jobs) enxergam sucesso. Confirmei: perfil inexistente gera `NoneType has no len()`, grava `ne.json` e sai com rc=0. Falhas parciais e bloqueio viram "zero resultado". |
| 9 | L83 | `open(..., "w")`: sobrescreve. Sem sufixo de data, sem escrita atômica (tmp+rename) e sem append. | Reexecutar sobrescreve o histórico. Um crash no meio deixa JSON truncado. Sem dedupe entre execuções. |
| 10 | (ausente) | Sem retry, backoff, limitação de taxa, proxy, rotação de identidade, cookies ou sessão persistente. | Tudo sai do mesmo IP com o mesmo UA. Primeiro 429 ou captcha é fatal e silencioso. |
| 11 | L25 (`headless` padrão `false`), L29-31 | UA fixo `Chrome/120` mas Playwright 1.47 traz um Chromium mais novo (inconsistência de fingerprint). Headless sem stealth (`navigator.webdriver` etc.). | Fácil de classificar como bot com o aumento de volume. Em servidor sem display o padrão `false` quebra. |
| 12 | L85, L87 etc. | `print` em vez de `logging`. `KWAI_LOG_LEVEL` do `.env.example` não é lido. Sem métricas, sem IDs de execução. | Sem observabilidade. Não dá para medir taxa de falha, nem montar alertas. |
| 13 | L24-32 | Só 5 variáveis lidas. `KWAI_OUTPUT_DIR`, `KWAI_DEFAULT_LIMIT_*`, `KWAI_LOG_LEVEL` não existem no código. Sem fila, agendamento ou checkpoint. | Cada keyword exige um processo lançado de fora. |
| 14 | L127-130 | Engajamento ausente vira `0`. | Qualidade de dados: 0 e "desconhecido" ficam indistinguíveis. |

## 4) O que já ajuda a escalar
- **Isolamento total por execução**: processo, browser e contexto novos, sem estado global (L22-32 só config). Por isso paralelizar com N processos é trivial e seguro.
- **Estratégia certa de captura**: SSR (`__NUXT__`) e XHR de feeds evitam parsear DOM e reverter assinaturas. É a parte mais barata de manter.
- **Dedupe por ID** dentro da execução (L197, L249, L263) e normalização de data e de texto (`_normalizar_data`, `html.unescape`).
- **Fechamento do browser em `finally`**: não vaza processos Chromium em erro (não verifiquei órfãos explicitamente).
- **Contrato de saída estável**: JSON com schema. `_montar_postagem` é uma função pura, fácil de testar e de mover para um worker.
- **Config por env** para timeouts e esperas (parcial), o que permite ajuste sem alterar o código.
- Funções separadas por modo. Dá para extraí-las e chamá-las num worker que reuse o browser.

## 5) Medições
Máquina de 16 vCPU e 32 GB, headless, IP residencial, sem proxy. Memória medida por PSS somando o processo Python e todos os filhos (Chromium), com amostragem de 0,2 s. Total de 8 execuções.

| Execução | Itens | Tempo | Pico de memória (árvore, PSS) | Python (RSS) | Processos |
|---|---|---|---|---|---|
| `busca parkour --limit 50` #1 | 24 | 8,1 s | 499 MB | 34 MB | 8 |
| `busca parkour --limit 50` #2 | 24 | 8,0 s | 520 MB | 34 MB | 8 |
| `usuario parkourcity --limit 50` #1 | 20 | 14,8 s | 539 MB | 43 MB | 8 |
| `usuario parkourcity --limit 50` #2 | 20 | 14,9 s | 545 MB | 43 MB | 8 |
| 3x `busca` em paralelo | 24 cada | 8,4 a 8,6 s (parede 8,7 s) | ~370 MB cada | 35 MB | 8 cada |
| `usuario naoexiste_zzz_98765` | 0 (`[]`) | 6,4 s | 486 MB | 34 MB | 8 |

Observações:
- **Tempo é dominado pelas esperas fixas.** Busca: 6 s de `wait_after_load` mais ~2 s de startup. Perfil: 4 s mais 4 rolagens vazias x 2 s (L255-268). Não há ganho de ajustar o código sem tocar as esperas.
- Memória por instância: **~0,4 a 0,55 GB**. O Python é só 35-45 MB. O resto é Chromium (processos de browser, GPU, renderer, utility).
- Paralelismo de 3 buscas não degradou o tempo (8,4-8,6 s contra 8,0 s sequencial), e a memória PSS por instância caiu (páginas compartilhadas). Em 16 vCPU o limite não foi CPU nesse teste, e sim o IP único.
- Nenhum bloqueio nem captcha nas 8 execuções (volume baixo e IP residencial). Isso **não** prova que sobrevive a volume.
- **Resultados de busca variam entre execuções**: duas buscas idênticas tiveram só 1 ID em comum nos 24 itens. A segunda XHR capturada trouxe 10 itens (a primeira, 14). A busca é personalizada ou randomizada, sem ordem estável. Não há reprodutibilidade nem cursor.
- Confirmei com medição o teto de 24 (busca) e 20 (perfil) e o `rc=0` em erro, já vistos no relatório prévio.

## 6) Estimativa 10x / 100x / 1000x
Base (1x): 1.000 keywords e 1.000 perfis por dia, no formato atual (sequencial, um browser por chamada). Tempos: busca ~8 s e 24 posts; perfil ~15 s e 20 posts.

| Escala | Volume/dia | Posts úteis/dia (teto) | Tempo sequencial | Instâncias para 24 h | RAM de pico | Custo de infra (ordem de grandeza) | O que quebra primeiro |
|---|---|---|---|---|---|---|---|
| 1x | 1k kw + 1k perfis | ~44 mil | ~6,4 h | 1 | ~0,5 GB | 1 VM pequena, ~US$ 15-30/mês | Nada de infra. O limite é a qualidade (24 e 20 itens). |
| 10x | 10k + 10k | ~440 mil | ~64 h | 3-4 em paralelo (4 GB RAM) | ~2 GB | 1 VM de 4 vCPU, ~US$ 60-100/mês | Single-IP. O Kwai tende a limitar por IP e por padrão de tráfego. Falhas silenciosas (`rc=0`) sem alarme. |
| 100x | 100k + 100k | ~4,4 milhões | ~640 h | 27-40 instâncias (15-20 GB) | ~20 GB | 4-6 VMs, ~US$ 500-900/mês, mais proxy residencial (tráfego pequeno, ~2-4 MB por página, ~1 TB/mês, centenas a milhares de US$) | Bloqueio por IP e fingerprint. Custo de proxy domina. Startup do browser por chamada desperdiça ~40% do tempo. |
| 1000x | 1M + 1M | ~44 milhões, só em tese | ~6.400 h | 270-400 instâncias | ~200 GB | Cluster dedicado, dezenas de milhares de US$/mês, só com proxy rotativo robusto | Praticamente tudo: anti-bot, proxy, observabilidade, deduplicação, armazenamento (milhões de JSON pequenos), orquestração. Abordagem de browser completo deixa de ser economicamente razoável; seria preciso API/HTTP direta. |

Pontos de atenção:
- Os números da coluna "Posts úteis" são **tetos teóricos**. Perfil entrega só os últimos 20 posts (sem histórico) e a busca é não reprodutível (item 5). Para "milhões de posts" por perfil é impossível sem paginação funcional. Ex.: 1 M posts por busca a 24 por consulta pede ~42 mil keywords distintas e muita repetição.
- Comentários: **0 em qualquer escala** sem sessão autenticada, o que traz o problema legal da seção 8.
- Os custos de VM são estimativas para a ordem de grandeza (instâncias sob demanda genéricas). Proxy é a maior incerteza e depende do bloqueio real.
- Reduzir esperas fixas (6 s e 4 s para ~1-2 s com `expect_response`) e reusar um browser com N páginas cortaria o tempo por item em 3-5x, o que desloca todos os números acima.

## 7) Roadmap priorizado

| Prio | Ação | Esforço | Efeito |
|---|---|---|---|
| 1 | Sair com `rc != 0` em erro; distinguir `bloqueado`, `sem_resultado`, `erro_rede`, `parse` no log e no JSON de saída; remover `except: pass`. | P | Orquestrador enxerga falhas. Pré-requisito para tudo. |
| 2 | Trocar `print` por `logging` JSON (run_id, alvo, duração, nº de itens, status HTTP). Ler `KWAI_LOG_LEVEL`. | P | Observabilidade mínima. |
| 3 | Trocar esperas fixas por `page.expect_response` / `wait_for_load_state` com timeout e retry com backoff exponencial e jitter. | P | 3-5x menos tempo por item. Menos perda por rede lenta. |
| 4 | Persistência: escrever em arquivo temporário e renomear, nome com timestamp ou ID de execução, saída em JSONL append e dedupe por `id` (SQLite ou Parquet). | P/M | Idempotência, sem sobrescrita, sem JSON truncado. |
| 5 | Worker de longa duração: um browser reaproveitado, N contextos/páginas em `asyncio`, reciclagem a cada X páginas para controlar memória. | M | 2-4x de throughput por GB. Remove o custo de startup. |
| 6 | Fila de tarefas (Redis/RQ, Celery ou Cloud Tasks) com tabela de checkpoint (alvo, cursor, última execução, tentativas) e agendador. | M | Várias máquinas, retomada após falha, sem reprocessar. |
| 7 | Paginação real: descobrir o endpoint de feed e usar `pcursor` via `page.request` (ou `httpx` com os cookies da sessão), em vez de rolar a página. Teste automatizado do teto (24/20). | M/G | Remove o teto de 24/20. É o desbloqueio de volume. |
| 8 | Camada anti-bot: proxy rotativo (residencial) por contexto, UA coerente com a versão do Chromium, headers/locale/timezone consistentes, limitação de taxa por IP, circuito (circuit breaker) em 403/429/captcha. | M/G | Sobrevive a 10-100x. Custo recorrente de proxy. |
| 9 | Contrato de qualidade: validar o schema na saída, `null` em vez de `0` para ausente, alerta quando o parse do `__NUXT__` falha ou quando o número de itens cai abaixo de um piso. | P/M | Detecta quebra de layout rápido. |
| 10 | Comentários: decidir a política. Opção legítima: abrir mão. Opção G: conta/sessão própria (ver seção 8). | G | Só se houver base legal. |
| 11 | Testes com fixtures gravadas (HAR) para os três modos e CI. | M | Manutenção sustentável diante de mudanças do Kwai. |

## 8) Riscos legais, ToS e anti-bot
- **Termos de Serviço**: coleta automatizada de plataformas sociais costuma ser vedada pelos ToS. Conferir os termos vigentes do Kwai antes de operar em volume. O risco aumenta com escala e com uso comercial. Este relatório não é parecer jurídico.
- **Dados pessoais (LGPD/GDPR)**: nome de usuário, ID, texto e engajamento ligados a pessoas são dados pessoais. Coleta em massa precisa de base legal, minimização, retenção definida e canal de remoção. Comentários agravam (texto livre de terceiros).
- **Login e conta**: usar sessão autenticada para ler comentários (que o candidato descartou) tende a violar os ToS de forma mais clara do que ler páginas públicas, e expõe a conta ao banimento. Não recomendado sem autorização expressa.
- **Anti-bot**: headless sem stealth, UA fixo desatualizado, IP único, esperas regulares e zero aleatoriedade são sinais fáceis. A consequência prática é rate limit, captcha, soft-block (devolver conteúdo diferente, como a busca com vídeos sem relação) e bloqueio de IP. **O soft-block é perigoso porque este código o trata como sucesso**: grava dados errados com `rc=0`.
- **Contornar proteções** (captcha solvers, falsificação agressiva de fingerprint) agrava o risco jurídico. Ficar em tráfego moderado, identificável quando possível, e respeitar `robots.txt` e limites é a posição mais defensável.
- **Dependência de endpoints não documentados** (`outer`, `getComments/list`, `__NUXT__`): sem contrato, podem mudar a qualquer momento. Planejar monitoramento e manutenção contínua.

## Reprodutibilidade
Scripts e saídas das medições: `meas/`(ambiente de avaliação)`run.py` mede tempo e PSS da árvore de processos). Foi instalado `psutil` no venv do ambiente de avaliação para isso. O checkout do PR não foi modificado.

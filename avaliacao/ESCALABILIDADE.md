# Análise de escalabilidade: PR #3 (teusdev7) - coletor Kwai, Nível 1

Caminhos relativos a `kwai_collector/` no checkout `(ambiente de avaliação)`. Análise informativa: escalar é objetivo dos níveis 2/3, não do nível 1.

## 1) Veredito

**Não escala como está; escala com ressalvas se tratado como biblioteca de clientes (não como pipeline).**
É um CLI síncrono, de processo único, sem fila, sem banco, sem proxy, sem métricas. Serve para dezenas de alvos por dia, não para milhares de keywords/perfis.
O que aproveita: parsers e o assinador local (rápido, sem Android, sem serviço externo) e o `RequestRateLimiter` com `Retry-After`. O que impede: identidade única, saída em arquivo JSON, busca com teto de 5 páginas e zero tratamento de bloqueio.

## 2) Como funciona hoje

- **Modelo**: 100% síncrono e sequencial. `argparse` -> um comando -> loop de páginas com `time.sleep`. Sem `asyncio`, sem threads, sem multiprocessing. Um comando processa um alvo por vez (`cli_collect.py:565` é um `sleep` entre posts no `coletar`, que é fixo em 10 posts, `cli.py:~92 MAX_POSTS`).
- **Busca** (`clients/kwai_client.py:43`): `httpx.post` avulso por página (nova conexão TCP/TLS cada vez), endpoint web PWA `/rest/o/w/pwa/v2/search/word/outer`, `count=10`, `max_paginas=5` fixo (`:81`), sem flag de CLI. Teto: 5x10 = no máximo ~50 posts por keyword.
- **Perfil** (`clients/profile_client.py:64`): `httpx.post` avulso, endpoint `/rest/o/w/pc/feed/profile`, 20 posts/página, pagina até cursor vazio/repetido (`:160-185`). Acumula tudo em lista (`:200`, `:210`) e só grava no fim (`cli_commands.py:~145`, `salvar_json` em `cli_utils.py:69`).
- **Comentários**: dois caminhos (`cli_comments.py:166-175`). Até 20: "tiny" API `api.kwai-pro.com` (`clients/tiny_comment_client.py:21-24`, `httpx.post` avulso, tenta dois hosts em sequência, sem retry nem backoff). Acima de 20 ou `--resume` ou `todos`: cliente mobile `LiveCommentClient` (`clients/live_comment_client.py`), host `api2-us.kwaipros.com`, `httpx.Client(http2=True)` criado uma vez por instância (`:63`) e reaproveitado entre páginas, 20 comentários/página, assinatura local por página.
- **Estado global**: `settings = Settings()` no import (`config.py:88`, lê `.env` do cwd), `logging.basicConfig` no import (`cli.py:78`) e defaults de função amarrados a `settings.*` na definição (`kwai_client.py:17-18,82`; `profile_client.py:40-41,140`). Não impede multiprocessos (cada processo recarrega), mas impede reconfigurar por job dentro de um mesmo worker.

## 3) Gargalos e bloqueadores

| # | Evidência | Impacto em escala |
|---|---|---|
| 1 | **Execução síncrona e serial**: `kwai_client.py:86-90`, `profile_client.py:150-176`, `live_comment_client.py:248-297`. | Throughput = 1 requisição por vez (~0,6-0,75 s de latência medida). Teto físico ~1.800 posts/min no perfil e ~1.700 coment./min sem pausa; com defaults (2 s de pausa) cai para ~440 coment./min. Sem paralelismo entre alvos. |
| 2 | **Sem reaproveitamento de conexão em busca/perfil/tiny/detalhe**: `httpx.post(...)` em `kwai_client.py:43`, `profile_client.py:64`, `tiny_comment_client.py:~120`, `httpx.get` em `post_detail_client.py:575`. Também sem `timeout` explícito (usa 5 s default do httpx) em busca/perfil. | Novo handshake TCP+TLS por página (medido: ~8% mais lento, 6,5 s vs 5,9 s em 10 páginas; em 1000 alvos vira milhares de handshakes e portas efêmeras). Timeout de 5 s gera falsos erros sob carga. Só os comentários mobile reusam `httpx.Client`. |
| 3 | **Rate limiter por instância, em memória, sem sincronização** (`request_rate_limiter.py:49-77`, estado `last_request`/`not_before` em atributos; instanciado dentro de `LiveCommentClient.__init__`, `live_comment_client.py:68`). Cobre só comentários mobile. Busca/perfil usam apenas `time.sleep(delay)` com `delay=0` por padrão (`config.py` `delay`). | Com N processos, cada um acha que é o único: o IP vê N vezes a taxa. Um 429 em um worker não desacelera os outros. Não há orçamento global por IP/identidade. Busca e perfil por padrão rodam **sem pausa nenhuma**. |
| 4 | **Retry sem jitter e sem `Retry-After` em busca/perfil**: `kwai_client.py:~70` (`backoff_base * 2**tentativa`), `profile_client.py:84,103`; só 3 tentativas; dois laços de retry diferentes (0-based vs 1-based). Só `LiveCommentClient` respeita `Retry-After` (`live_comment_client.py:148-150,184-185`). Tiny: nenhum retry (`tiny_comment_client.py:~130-160`). | Retries sincronizados (thundering herd) em várias máquinas; 3 tentativas com 1s+2s esgotam em 3 s, ou seja, um 429 de janela de minutos aborta o perfil inteiro e perde tudo (ver #7). Sem circuit breaker. |
| 5 | **Identidade única e fixa, sem proxy nem rotação**: comentários mobile usam `client_key=3c2cd3f3` e `User-Agent: kwai-android/10.3.20.540101` constantes (`security/local_comment_request_provider.py:33-40`), `context_id` aleatório fixo por processo (`kwai_lite_103_offline_sig3_signer.py:134`), `llsid` aleatório por post (`live_comment_client.py:222`). Não há `did`, `egid` nem token no caminho mobile (anônimo). No tiny, `did`/`egid` vêm só de env `KWAI_DID`/`KWAI_EGID` (`cli_builders.py:59-80`), uma identidade para tudo. Não existe parâmetro de proxy em nenhum cliente (`grep proxy` vazio; `httpx` ainda honra `HTTP(S)_PROXY` do ambiente, mas por processo, sem rotação). | Todo o tráfego sai com o mesmo IP, UA e `client_key`. Ao primeiro desafio/ban de IP, a coleta para; não há troca de identidade. Para escala é preciso pool de IPs/proxies residenciais (custo recorrente) e fingerprint por sessão. |
| 6 | **Zero detecção de bloqueio/anti-bot**: nenhum tratamento de 403, captcha, `result != 1` além de abortar (`live_comment_client.py:174-181` aborta com `CommentCollectionInterrupted`), nem de resposta HTML/vazia. Busca/perfil: 4xx != 429 faz `raise` imediato (`kwai_client.py:~56`); resposta 200 com `feeds` vazio é lida como "fim" (`profile_client.py:~166`, `kwai_client.py:~95`). | **Bloqueio silencioso vira "coleta concluída"**: shadow-ban/200 vazio trunca perfil sem erro. Sem métrica de taxa de sucesso, o operador não percebe. |
| 7 | **Memória e persistência do perfil**: `get_all_profile_posts` acumula todos os posts crus (`profile_client.py:200,210`), depois `normalize_posts(raw_posts)` cria uma segunda lista (`cli_commands.py:~140`), e só então `salvar_json` (`cli_utils.py:69`, `indent=2`). | Medido: ~55 KB de heap Python por post cru (tracemalloc, 199 posts = 10,9 MB). Extrapolação linear: 7.391 posts = ~400 MB só no cru, mais a cópia normalizada (estimativa ~500-700 MB de pico). 10 perfis desse tamanho em paralelo = 5-7 GB. Sem gravação parcial, falha aos 10 min de coleta perde tudo (relatório prévio: 10m56s). |
| 8 | **Comentários: checkpoint reescreve o arquivo inteiro a cada página**: `comment_checkpoint.py:79-98` (JSON `indent=2`, `fsync`, `os.replace`) e `live_comment_client.py:225-233,269` (`snapshot()` copia a lista toda e `_unique_comments(all+comments)` reconstrói a lista a cada página). | Custo O(n²) no tamanho do post. Medido: 18 ms (1,5 mil), 65 ms (10 mil), 304 ms (50 mil comentários, 16 MB por gravação) a cada página de 20. Em posts virais (100 mil+), cada página gasta mais em I/O+CPU que em rede. O bom: gravação atômica e idempotente (`os.replace`). |
| 9 | **Persistência é arquivo local sem coordenação**: `output_dir/<usuario>_posts.json`, `busca_<kw>.json`, `<photo_id>_comentarios.json` (`cli_commands.py`, `keyword_comment_collection.py:~270`). `salvar_json` escreve direto em `open("w")`, **sem tmp+rename** (`cli_utils.py:69`). `DEFAULT_OUTPUT_DIR=samples` (`cli_parsers.py:16`). | Dois processos no mesmo alvo sobrescrevem um ao outro; falha no meio deixa JSON truncado. Nome de arquivo por chave dificulta incremental/dedup global. Em várias máquinas não há storage comum. Sem esquema de saída em lote (JSONL/Parquet), sem dedup entre execuções. |
| 10 | **`--resume` só existe para comentários mobile e é por post**: checkpoint por `photo_id` (`cli_comments.py:~363`), valida `photo_id`/`user_id` (`live_comment_client.py:211-214`). Não há checkpoint de perfil nem de busca, nem estado de "o que já foi coletado". Idempotência: reexecutar sobrescreve; `_save_individual_comments` não sobrescreve com lista vazia (`keyword_comment_collection.py:~270`). | Retomada de lote (milhares de posts) não existe. Para um lote seria preciso um manifesto por job. Dois workers no mesmo `photo_id` brigariam pelo mesmo `.json` de checkpoint (rename atômico, mas "último ganha"). |
| 11 | **Busca com teto de 5 páginas** (`kwai_client.py:81`, ~49 posts) e uma keyword por execução. `search_posts` ignora `pcursor` inicial além do índice; `pcursor` é o índice inteiro `range(max_paginas)` (`:88`), não um cursor opaco do servidor. | Para "milhares de keywords" a cobertura por keyword é de ~50 resultados; não dá para aprofundar sem editar código. Também não há paginação de página de busca "orgânica" por cursor. |
| 12 | **Assinador local acoplado a uma versão do APK**: `kwai_lite_103_offline_sig3_signer.py:136-139` recusa qualquer `app_package`/`appver` diferente de Kwai Lite 10.3.20.540101; blob de 151.616 bytes com SHA-256 fixo (`:44-45,70-73`); só assina `POST /rest/o/comment/list/v2` (`:152`). | Medido: **0,19 ms/assinatura** (5.400/s em 1 thread; 3.800/s em 4 threads, GIL), 2,9 ms na primeira chamada (carrega material), ~20 MB RSS. Ou seja, CPU **não** é gargalo (a rede é 3.000x mais lenta). O risco é de **durabilidade, não desempenho**: quando o Kwai rotacionar a versão mínima/chaves do app, 100% dos comentários param ao mesmo tempo, em todas as máquinas, e consertar exige novo reverse engineering do APK. Thread-safety: contador protegido por `threading.Lock` (`:153,171-172`) e `context_id` por instância, então multi-thread no mesmo processo é seguro; porém o `context_id` único por processo torna o tráfego correlacionável. |
| 13 | **~1.400 linhas de código morto** (`real_comment_client.py`, `mobile_http_comment_client.py` 674, `mock_comment_client.py`, `adb_comment_provider.py` 248, `callback_signature_provider.py`); `config.py` ainda expõe `adb_path`, `adb_serial`, `mobile_auth_endpoint/token`. | Sinaliza caminhos alternativos: (a) ADB num dispositivo/emulador real para assinar, (b) `KWAI_MOBILE_AUTH_ENDPOINT`: um **serviço HTTP externo de assinatura** (`http_mobile_request_provider.py`, ativo via `cli.py:~98-110`). O (b) é o único gancho de arquitetura distribuída que já existe (assinador como serviço central), mas não vem implementado, e (a) não escala (1 dispositivo = 1 worker). Para escala, (b) é a direção certa. |
| 14 | **Sem fila, agendador, banco, métricas, tracing**. Observabilidade = `logging.info` em texto, sem contadores (requisições, 429, bytes, latência, falhas por alvo). `httpx` logger silenciado (`cli.py:~84`). | Não há como saber taxa de bloqueio, custo por post, ou estado de um lote. Sem dead-letter nem reprocessamento. |
| 15 | **Sem timeout nem limite de tamanho de resposta** em busca/perfil; `post_detail_client.py` (762 linhas) faz parsing de HTML/JS com varredura de caracteres (`:132-177,419-459`, scanner manual de JSON embutido). | CPU-bound e frágil para volume; qualquer mudança de layout do site quebra o detalhe. Não é caminho crítico (perfil/busca usam JSON), mas aparece em `coletar`. |

## 4) O que já ajuda a escalar

- **Assinatura local barata e sem dependência de dispositivo**: 0,19 ms, thread-safe, sem Android. Elimina o maior bloqueador típico (farm de aparelhos). Pode rodar em qualquer worker.
- **Cliente mobile de comentários bem comportado**: `httpx.Client` com HTTP/2 reaproveitado (`live_comment_client.py:63`), `Retry-After` respeitado com `defer_for` (`:148-150`), backoff exponencial limitado a 60 s (`:184`), 429/5xx/501 tratados, erro não vaza texto da API.
- **Checkpoint atômico** (tmp + fsync + `os.replace`, `comment_checkpoint.py:79-98`), validado por schema estrito, sem credenciais; retomada correta por cursor e `llsid`.
- **Dedup por id** em todos os caminhos e **detecção de cursor repetido**.
- **Parsers puros e modelos pydantic** (`parsers/`, `models/`): separáveis e testáveis offline (235 testes sem rede). Reutilizáveis num worker de fila.
- **Configuração por env var tipada** (`pydantic-settings`, prefixo `KWAI_`), amigável a contêiner.
- **Endpoints web públicos** de perfil/busca funcionam sem login, cookie, `did` ou token; custo operacional baixo.
- O **ponto de extensão `MobileRequestProvider`** (`security/signature_provider.py`) já isola "preparar requisição assinada" atrás de uma interface, o que permitiria trocar o assinador local por um serviço.

## 5) Medições (reais, rede liberada, ~51 requisições, perfil público parkourcity, sem credenciais)

Ambiente: venv do PR3, Python 3.12, uma máquina, uma conexão. Script em `(ambiente de avaliação)` (`net.py`, `com.py`, `sign.py`, `ckpt.py`).

| Medida | Resultado |
|---|---|
| Import do pacote (settings + logging + pydantic) | ~72 ms |
| Perfil, 10 páginas, `httpx.post` avulso (como o código), delay 0 | 6,48 s, 199 posts; latência média 648 ms (min 554, máx 1.019); **~1.840 posts/min** |
| Perfil, 10 páginas, `httpx.Client` reaproveitado | 5,92 s; latência média 592 ms; **~2.020 posts/min** (+10%) |
| Busca, 1 página | 748 ms, 10 posts (5 páginas ~3,7 s, ~50 posts: ~800 posts/min só se pausa 0) |
| Comentários mobile, 10 páginas (200 comentários), `page_delay=0`, 3 execuções | 7,64 / 7,15 / 6,09 s; ~610-760 ms/página; **~1.570-1.970 comentários/min**; sem 429 nem bloqueio em 30 páginas seguidas a ~1,4 req/s |
| Assinatura local | 0,19 ms/assinatura (5.400/s), 3.800/s com 4 threads, primeira chamada 2,9 ms |
| RSS do processo após rodar perfil+busca | ~69 MB para 200 posts |
| Heap Python por post cru | ~54,8 KB (JSON equivalente ~10,3 KB: expansão ~5x) |
| Checkpoint de comentários (salvar) | 18 ms (1,5 mil), 65 ms (10 mil), 304 ms (50 mil) por página |

Throughput por instância (um processo, sequencial). "Defaults" usa as pausas padrão do projeto (perfil/busca `delay=0`, comentários `mobile_page_delay=2,0 s`):

| Operação | Sem pausa (teto medido) | Com defaults / pausa 1 s |
|---|---|---|
| Posts de perfil | ~1.800-2.000 posts/min | defaults: ~1.800/min; delay 1 s: ~730/min (compatível com 7.391 em 10m56s do relatório prévio) |
| Comentários | ~1.600-1.900/min | defaults (2 s): ~440/min; intervalo 1 s: ~700/min |
| Busca | 10 posts/0,75 s, mas teto 50 posts/keyword | ~16 keywords/min (5 páginas, delay 0), ~230k keywords/dia teórico, só ~50 posts cada |

Ressalva: medições curtas, de uma máquina, sem teste de limite do servidor. A ausência de 429 em ~50 requisições **não prova** tolerância em escala; o limite real (por IP/dia) é desconhecido.

## 6) Estimativa por fator (base: 1 instância)

Referência "1x": ~1 perfil de 7 mil posts (~4-11 min) e ~1,5 mil comentários (~1 min) por execução; dezenas de alvos/dia.

| Fator | Alvo ilustrativo | O que quebra primeiro |
|---|---|---|
| **10x** (centenas de alvos/dia, ~10 processos na mesma máquina/IP) | ~70 mil posts, ~15 mil coment. | (1) **Orquestração**: não há fila; seria `xargs`/cron manual. (2) **Memória**: 10 perfis grandes em paralelo = 5-7 GB. (3) **Rate limit por IP** (limitadores por processo somam 10x a taxa; busca/perfil sem pausa). Primeiros 429s; perfil perde tudo (retry de 3 s, sem `Retry-After`). (4) Arquivos de saída sobrescritos. |
| **100x** (milhares de alvos/dia, ~1 M posts, ~150 mil coment., várias máquinas) | | (1) **Bloqueio/ban de IP** com identidade única (nenhum proxy/rotação, `client_key` e UA fixos): a coleta degrada para 200 vazios lidos como "fim" (truncamento silencioso). (2) Sem storage/dedup comum e sem checkpoint de perfil/busca: falha parcial = reexecutar. (3) Sem métricas, ninguém percebe. (4) Handshake por requisição esgota portas/CPU. (5) Posts virais: checkpoint O(n²). |
| **1000x** (dezenas de milhares de perfis/dia, milhões de posts, ~10 M+ comentários) | | (1) **Custo e disponibilidade de IP/proxies** e política anti-bot do Kwai, não código; sem pool, impossível. (2) **Fragilidade do assinador**: um único update do app derruba todos os comentários de todos os workers ao mesmo tempo. (3) Falta de banco/fila/orquestração/dedup/backfill/agendamento incremental (recoleta de perfis, só novos posts). (4) Busca com teto de 50 não cobre a descoberta. (5) Risco jurídico e de bloqueio contratual (ver 8). Em 1000x o gargalo é o acesso, não CPU nem memória. |

Cálculo de apoio: 1 M posts/dia a ~1.800 posts/min = ~9 h de 1 worker (viável em CPU/rede, mas só se o IP aguentar). 10 M comentários/dia a ~1.700/min = ~98 h de worker, ou ~5-10 workers com taxa por IP muito acima do que um cliente real faria.

## 7) Roadmap priorizado (esforço: P pequeno, M médio, G grande)

1. **Cliente HTTP único e reaproveitado** com timeout explícito, HTTP/2, pool, retry unificado com jitter e `Retry-After` para busca, perfil, tiny e detalhe; remover os dois laços duplicados. (**P**)
2. **Rate limiter compartilhável**: token bucket por host/IP no Redis (ou arquivo/lock se for 1 máquina), com `defer_for` global em 429. Defaults de `delay` > 0 em busca/perfil. (**M**)
3. **Detecção de bloqueio** e classificação de resposta: 403/captcha/HTML/200 vazio suspeito vs fim real; falhar alto em vez de truncar; contador de sucesso/erro por alvo. (**M**)
4. **Persistência incremental**: escrever JSONL por página (append) para perfil/busca/comentários, com manifesto de cursor por alvo; `--resume` em perfil e busca; checkpoint de comentários só com cursor+offset (e comentários em JSONL append), eliminando o O(n²). Gravação atômica no `salvar_json`. (**M**)
5. **Remover estado global**: `Settings` passado por parâmetro, `basicConfig` em `main()`, defaults não amarrados ao import. Necessário para workers reentrantes. (**P**)
6. **Paginação de busca real** (cursor do servidor, `--max-pages`/até esgotar) e múltiplas keywords por entrada em lote. (**P**)
7. **Modelo de job + fila** (ex.: Redis/RQ, Celery ou fila SQS) com jobs `search(kw)`, `profile(user)`, `comments(photo)` idempotentes, chave de dedup e DLQ; saída em Postgres/Parquet/S3 com `ON CONFLICT` por `photo_id`/`comment_id`. (**G**)
8. **Proxies e identidade por sessão**: pool com rotação por job, UA/`client_key` por sessão, afinidade IP-`context_id`/`llsid`, backoff por IP. Verificar custo e viabilidade. (**G**, e contínuo)
9. **Observabilidade**: métricas Prometheus (req/s, 429, latência, bytes, bloqueios, posts/min, backlog), logs estruturados, alertas de queda de taxa de sucesso. (**M**)
10. **Mitigar dependência do APK**: isolar o assinador num serviço próprio versionado (já há o gancho `KWAI_MOBILE_AUTH_ENDPOINT`), testes de canário que detectam quebra de assinatura, plano B (`tiny` ate 20 comentários). Decidir se a aposta é manter engenharia reversa. (**G**, risco permanente)
11. **Remover os ~1.400 linhas mortas** (adb/mobile http/mock/callback) ou mover para `contrib/`; reduz superfície e confusão. (**P**)
12. **Perfil em streaming**: processar página a página (gerador) e gravar, mantendo memória O(1) por perfil. (**P**, parte do item 4)

Ordem sugerida para ganho/risco: 1, 5, 4(parcial), 3, 2, 6, depois 7+9, e 8 como decisão de produto.

## 8) Riscos legais, ToS e anti-bot (objetivos)

- **Engenharia reversa de proteção anti-bot**: o assinador reimplementa `sig3`/`__NS_sig3`/`__NStokensig` do app Kwai Lite a partir do APK (151 KB de tabelas extraídas do binário, `security/kwai_lite_103_sig3_material.bin`). Isso contorna uma medida técnica de acesso. Risco: violação de ToS do Kwai, possível enquadramento em contornar medida de proteção (DMCA 1201 / equivalentes locais; revisar com jurídico), distribuição de material extraído de software de terceiros no repositório.
- **Impersonação de cliente oficial**: usa `User-Agent kwai-android/10.3.20.540101`, `client_key` do app e host de API móvel (`api2-us.kwaipros.com`) sem ser o app. Tende a ser tratado como acesso não autorizado/automatizado.
- **Endpoints web (busca/perfil)** são públicos e sem login, mas o scraping automatizado em volume costuma violar os termos de uso; sem proxy/rate adequados, gera ban de IP e potencial notificação.
- **LGPD/GDPR**: comentários e perfis são dados pessoais (nome, id, avatar, texto, data), coletados sem consentimento em lote e armazenados em JSON local sem política de retenção/anonimização/segurança. Escalar amplifica a obrigação de base legal, minimização, DPIA e direito de exclusão. `bio`, `nome`, `avatar` (`cli_builders.py` `montar_perfil`) são coletados sem necessidade comprovada.
- **Volume agrava risco**: 10x já exige IPs além do próprio; proxies residenciais têm questões éticas e contratuais próprias.
- **Dependência de terceiro**: a coleta pode parar de um dia para o outro por mudança do Kwai; sem contrato/API oficial não há SLA.
- Positivo: sem segredo commitado, log de depuração redige `did`/`egid`/`sig` (`tiny_comment_client.py:_registrar_tiny_request`(ambiente de avaliação)`parkourcity`.

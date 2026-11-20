# Análise de escalabilidade: PR #4 (Lucas7721), coletor Kwai, Nível 1

Código em `(ambiente de avaliação)`. Todos os arquivo:linha abaixo vêm daí. Relatório de avaliação prévio: `(ambiente de avaliação)`.

## 1) Veredito

- **Não escala como está.** É uma CLI síncrona de um processo só, sem estado, fila ou checkpoint. É correta para o Nível 1 e não é cobrada para escala.
- **Escala com ressalvas pequenas, em termos de código.** `client`/`parser`/`scraper` são camadas finas, quase puras e testadas. A migração para workers é barata (dias, não semanas). O mais caro é o que o código não tem: identidade, proxy, orquestração e persistência.
- **O que quebra primeiro**: no código, o rate limit global (`client.py:79-88`) e a falta de retomada. No ambiente real, a dependência de uma identidade de dispositivo única e de um sal de app fixo, que dá bloqueio/ban e revisão de ToS antes de qualquer volume.

## 2) Como funciona hoje

- Modelo: CLI Typer (`cli.py:54-90`). Cada execução faz uma coleta, guarda tudo numa lista em memória e grava um JSON no fim (`cli.py:31-51`).
- Busca: POST web JSON em `www.kwai.com`. Paginação por offset (`pcursor` numérico, `scraper.py:53-74`), 50 itens por página. Keywords em sequência (`scraper.py:51`).
- Perfil e comentários: API móvel anônima do Kwai Lite, três hosts em fallback (`client.py:17-21`, `158-181`). Cada request leva `sig` = MD5 dos parâmetros ordenados + sal fixo (`client.py:91-98`).
- Perfil: 30 posts por página, cursor opaco (`scraper.py:93-130`). Comentários: 50 por página (`scraper.py:140-172`). Respostas: 100 por página e uma chamada por comentário raiz com `sub_comment_count > 0` (`scraper.py:175-226`).
- Cada request chama `httpx.post(...)` solto (`client.py:111`), sem `Client` reaproveitado. Antes dele, `wait_delay()` dorme o resto de 1,5 s (`client.py:82-88`, `config.py:7`).
- Retry: até 3 tentativas, backoff `min(0.5*2^n, 8)` (`client.py:135`), só para 429/5xx/JSON inválido/erro de transporte. 4xx vira falha imediata.

## 3) Gargalos e bloqueadores

| # | Onde | Problema | Impacto na escala | Gravidade |
|---|---|---|---|---|
| 1 | `client.py:79-88` | Rate limit com `_last_request` global de módulo, **sem lock**, por processo. Sleep de no mínimo 1,5 s por request. | Teto de ~0,67 req/s por processo, mesmo com a API respondendo em 0,5 s (ver medições). Com threads, o estado global não é seguro (duas threads leem o mesmo `_last_request` e disparam juntas). Com vários processos, cada um tem o seu e ninguém coordena o total contra o Kwai. | Alta |
| 2 | `client.py:111` | `httpx.post` por chamada: abre conexão e TLS a cada request, sem pool, sem HTTP/2. | Na medição o ganho de reutilizar a conexão foi irrelevante (a latência é do servidor). Mesmo assim limita o paralelismo e impede configurar proxy/identidade por cliente. | Média |
| 3 | `config.py:19` (`settings = Settings()` no import), usado em `client.py:85,111,132,150` | Configuração global no import. Não há como ter dois clientes com configs, delays ou proxies diferentes no mesmo processo. Env inválido derruba tudo no import. | Impede múltiplas "identidades" ou perfis de rate limit por worker no mesmo processo. Com um processo por worker, vira não-problema. | Média |
| 4 | `client.py:25-26,29-57` | `SIG_SALT`, `CLIENT_KEY`, `APP_VERSION`, `did/vid/egid` e demais parâmetros do dispositivo são constantes. Todos os usuários desta ferramenta aparecem como o **mesmo dispositivo** Android emulado (`sdk_gphone_x86`). | Esta é a barreira real. Em volume, um único `did` com milhares de requests/dia é trivialmente identificável e bloqueável. Não há rotação de `did`/`session_id` estável por worker (só `session_id` e `timestamp` mudam por request, `client.py:101-105`). | Crítica |
| 5 | `client.py:91-98` | Assinatura MD5 + sal. Custo de CPU desprezível, thread-safe (função pura), determinística. Estabilidade: o sal é do app 10.3.20 (`client.py:24`). Uma atualização que troque o sal ou adicione `__NS_sig3` (o código já ignora esses campos, `client.py:95`) quebra tudo de uma vez. | Rodar em escala amplifica o risco: o sal é um ponto único de falha, sem health check, sem detecção ("erro de assinatura" aparece como `result != 1` genérico, `client.py:141-146`) nem fallback. | Alta (risco), Baixa (custo) |
| 6 | `client.py:125-138` | Retry sem jitter, sem `Retry-After`, sem circuit breaker, sem limite de orçamento por job. 429 tratado como erro transitório igual a 500. Os sleeps são números mágicos. | Em 100 workers, os retries ficam sincronizados e martelam o alvo (thundering herd). Sem adaptação, o 429 só gera 3 tentativas e falha. Não há diferenciação "estou bloqueado" vs "erro passageiro". | Alta |
| 7 | `client.py:162-177` | O fallback de hosts é por request, com ordem fixa. O primeiro host recebe todo o tráfego. Falha de host não é memorizada. | Cada request que falha no host 1 paga latência antes de ir ao 2. Sem balanceamento nem blacklist temporário. | Baixa |
| 8 | Nenhum proxy (`httpx.post` sem `proxy=`/`transport`) | Sem suporte a proxy, rotação de IP, ou fingerprint TLS/HTTP2 distinto. User-Agent fixo (`config.py:15-18`, `client.py:64`). | Um IP só. Bloqueio por IP/ASN em datacenter é provável acima de poucas centenas de requests/hora. A busca usa UA de Chrome com o stack TLS do httpx (JA3 de Python), o que diverge de um navegador. | Crítica |
| 9 | `cli.py:31-51`, `scraper.py` (listas `posts`, `result`) | Tudo acumulado em memória antes de gravar. "Tudo ou nada": se falha na página 900, perde as 899 anteriores. Nenhuma saída parcial. | Para um perfil de 100k posts, perde horas de trabalho em um erro tardio. Memória cresce linearmente (ver medições, ~17 KB/post em objetos Pydantic). Não bloqueia por memória até milhões, mas bloqueia por confiabilidade. | Alta |
| 10 | `cli.py:41-51` | Um arquivo JSON indentado por execução, sobrescreve silenciosamente o destino (`write_text`). Sem JSONL/append, sem particionamento, sem escrita atômica (tmp + rename). | Sem idempotência e sem dedup entre execuções. Dois jobs no mesmo `--out` se sobrescrevem. Impraticável juntar milhões de linhas em um JSON de lista. | Alta |
| 11 | `scraper.py:93-130,140-172` | Sem checkpoint/resume: o cursor existe só em variável local. Recomeçar = voltar ao início. | Combinado com o item 9, uma coleta longa não é retomável. | Alta |
| 12 | `scraper.py:42-79` | Busca: paginação por **offset** (`pcursor` numérico) com teto não medido; keywords sequenciais, uma busca só termina quando `limit` é atingido ou quando uma página não traz itens novos (`scraper.py:72`). O limite é global (soma de todas as keywords), não por keyword. | Para milhares de keywords por dia, é preciso um job por keyword com limite próprio; hoje a API da CLI mistura as keywords num só resultado e a primeira esgota o limite. O teto de profundidade do offset do Kwai não foi testado (não fiz paginação profunda) e é um risco desconhecido. | Média |
| 13 | `scraper.py:223` (loop de respostas) | Respostas: 1 request por comentário raiz com respostas, em sequência, 1,5 s cada. Post com 5k comentários raiz com respostas leva 2 h só nisso. | Throughput de comentários fica ordens abaixo do necessário para milhões. | Média |
| 14 | Todo o pacote | Sem fila, banco, agendador, métricas, healthcheck, logs estruturados. Logging é `basicConfig` com texto (`cli.py:23-26`). | Não há como saber a taxa de erro, a de bloqueio, o backlog ou a cobertura. Em escala, sem isso é pilotar às cegas. | Alta (operacional) |
| 15 | `parser.py`, `models.py` | Modelos Pydantic construídos por item e `model_dump` no fim; `ValidationError` não tratada (`cli.py:33-39`). Um item malformado pode derrubar a coleta inteira. | Em milhões de itens, a taxa de item estranho nunca é zero. Precisa de quarentena/dead-letter, não de traceback. | Média |

## 4) O que já ajuda a escalar

- **Separação em camadas.** `parser.py` é função pura (dict -> modelo, `parser.py:11-114`), `scraper.py` só orquestra paginação e `client.py` concentra I/O. Trocar `client` por uma versão async ou com pool muda um módulo.
- **Assinatura pura.** `create_signature` (`client.py:91-98`) não tem estado e é thread-safe. 168 mil assinaturas/s num núcleo, então nunca será gargalo.
- **Paginação defensiva.** `next_cursor` (`scraper.py:25-34`) trata cursor repetido e fim, dedup por id (`scraper.py:67-69, 121-123, 165-167`) e `to_int` devolve `None` em vez de inventar 0 (`parser.py:15-22`). Isso reduz lixo em reexecuções.
- **Erros tipados.** `TransientError`/`KwaiError`/`InvalidInput` já separam retentável de fatal, base para uma política de retry por classe.
- **Testes offline** (22 testes, 93% de cobertura, respx). Dá segurança para refatorar o client para async/pool mantendo o contrato do parser.
- **Contrato de saída claro** (`models.py`) e `collected_at` por execução (`scraper.py:47, 99, 211`), útil para versionar snapshots.
- **Medido**: o endpoint móvel aceitou 6 requests paralelos sem bloquear (ver 5), então não há trava de concorrência óbvia no servidor em baixo volume.

## 5) Medições

Rede real, perfil público `parkourcity`, sem credenciais, ~31 requests no total. Ambiente: venv `pr4`, Python 3.12. Scripts em `(ambiente de avaliação)`. As medições valem para este instante e esta rede (Brasil -> Kwai), não são benchmark estatístico: amostras de 6 a 8 requests.

| Medição | Resultado |
|---|---|
| Latência por request da API móvel (perfil, 30 posts) | 0,47 a 0,67 s (média ~0,58 s), 6 requests |
| Perfil 150 posts, `KWAI_REQUEST_DELAY=0` | 6 requests (1 user + 5 páginas), 3,5 s, ~43 posts/s |
| Perfil 60 posts, delay padrão 1,5 s | 3 requests, **3,56 s** (o sleep domina: ~1,5 s de espera para ~0,5 s de rede) |
| Comentários (3 posts, 15 a 22 comentários) | 1 a 2 requests por post, ~0,47 s por página (sem delay). Os posts eram pequenos: não medi um com milhares de comentários nem profundidade de cursor |
| Comentários, throughput efetivo no padrão | 50 comentários/página, 1 página a cada ~2 s (1,5 s de delay + 0,5 s de rede) = ~25 comentários/s teórico por instância, ~1.500/min, ~90 mil/h |
| Conexão nova vs reaproveitada (`httpx.Client`) | 0,56 a 0,67 s vs 0,52 a 0,95 s: **sem ganho mensurável**. A latência é do servidor, não do handshake |
| 6 requests em paralelo (threads, 1 `Client`) | 0,6 s de parede para 6 (todos 200), contra ~3,6 s sequencial. **Escala ~6x** neste teste curto |
| `create_signature` | 168 mil/s (CPU de um núcleo): irrelevante |
| Memória, perfil de 150 posts | pico `tracemalloc` ~2,5 MB (~17 KB/post); RSS máximo do processo (inclui Python, httpx, pydantic) ~53 MB |
| Tamanho do JSON | ~560 bytes/post indentado |

Extrapolação (não medida): 1 milhão de posts em memória seria ~17 GB de objetos Pydantic só na lista, mais o `json.dumps` do texto inteiro (~560 MB de string), mais as listas de `model_dump()`. Isso estoura em máquinas pequenas muito antes de a API ser o problema.

Não medi: comportamento sob 429 (não forcei), paginação profunda (>150 posts), HTTP real com proxy, bloqueio por volume. Por isso não afirmo qual é o limite do Kwai.

## 6) Estimativa de throughput (por instância e múltiplos)

Throughput de 1 instância, config padrão: 1 request a cada ~2 s (delay + latência) ~ 0,5 req/s ~ 43 mil requests/dia contínuos.

| Escala | Carga (exemplo) | O que acontece | Quebra primeiro |
|---|---|---|---|
| **1x** | Dezenas de keywords/perfis por dia | Funciona. Perfil de 1.000 posts: ~34 requests ~70 s. Comentários de um post com 1.000: ~20 páginas ~40 s | Nada, desde que a coleta não passe de alguns minutos (tudo ou nada) |
| **10x** | Centenas de keywords/perfis por dia, centenas de milhares de itens | Uma máquina com 5 a 10 processos/threads dá conta de CPU e rede. O delay de 1,5 s por processo vira o piso. | (a) Estado global de rate limit: ou 1 processo por job (sem coordenação), ou threads com race condition. (b) Perda de coleta por falha tardia. (c) Sem scheduler, é cron + shell. O Kwai ainda tende a tolerar, mas já com um único `did`/IP |
| **100x** | Milhares de keywords/perfis por dia, milhões de itens | Precisa de várias máquinas. 43 mil req/dia/instância x 100 = ~4,3 mi req/dia. | **Anti-bot**: um `did` e um IP para esse volume. Depois, memória/JSON único por job, falta de resume e de dedup entre execuções. O sal fixo vira risco sistêmico (uma mudança do app derruba tudo ao mesmo tempo, sem alerta) |
| **1000x** | Dezenas de milhões de posts, centenas de milhões de comentários | Requer pool de identidades/proxies residenciais, fila distribuída, storage colunar/objeto, deduplicação global, monitoramento, política de compliance. | O código atual é descartável nessa faixa: fica útil só `parser`/`models`. O custo e o risco passam a ser operacionais (proxies, bloqueio, ToS), não de CPU. Ver 8 |

## 7) Roadmap priorizado (P < 1 dia, M = 2 a 5 dias, G > 1 semana)

1. **(P) Transformar `client.py` em classe `KwaiClient`** com `httpx.Client` injetável, `Settings` injetado (remover `settings` do import, `config.py:19`) e rate limiter como atributo. Destrava múltiplas identidades no mesmo processo e simplifica testes. Dívida já apontada na avaliação.
2. **(P) Retry decente**: jitter, `Retry-After` em 429, parâmetros de backoff em `Settings`, orçamento máximo de tentativas por job; classificar "bloqueio" (429/403/captcha/assinatura inválida) separado de erro transitório (`client.py:125-146`).
3. **(M) Saída incremental**: gravar JSONL em modo append por página (iterador/gerador em `scraper.py` em vez de listas), escrita atômica e `--out` com partição (`keyword/data`). Resolve itens 9, 10 e o pico de memória.
4. **(M) Checkpoint/resume**: persistir o último cursor e o conjunto de ids vistos (SQLite local no começo) e reiniciar a partir dali. Dedup entre execuções fica quase de graça.
5. **(M) Rate limiter compartilhável**: token bucket por host/identidade, com lock (threads) e depois Redis (várias máquinas). Hoje é `time.sleep` por processo.
6. **(M) Camada async**: as funções do scraper são sequenciais mas sem estado cruzado; trocar `post_json` por `await client.post(...)` com `asyncio.Semaphore` por identidade é viável. Os testes de parser permanecem. O resultado da medição (6 paralelos em 0,6 s) sugere ganho real, mas precisa ser validado sob carga maior e com cuidado de ToS.
7. **(M) Pool de identidades e proxies**: um `did/vid/egid/ud` por identidade, rotação, quarentena de identidade bloqueada, proxy por identidade (sticky). Sem isso, o item 4 da tabela de gargalos é intransponível.
8. **(M) Observabilidade mínima**: contadores (requests, 2xx, 429, erros de assinatura, itens/s), logs JSON, alerta quando taxa de `result != 1` sobe. Detecta mudança de sal/versão do app.
9. **(G) Fila de jobs** (ex.: Redis/RQ, Celery ou Arq): job = (tipo, alvo, cursor), com idempotência pela chave, retries e dead-letter. Scheduler para recoleta periódica.
10. **(G) Storage**: Postgres (upsert por `id`) ou Parquet/objeto particionado, com `coletado_em` por observação (série temporal de engajamento).
11. **(G) Manutenção do sal e versão do app**: processo para extrair/atualizar sal e `APP_VERSION`, teste de fumaça diário contra um perfil público, feature flag de versão.
12. **(P) Pequenos reparos**: validar domínio da URL (`scraper.py:134`), tratar `ValidationError` (`cli.py:33-39`), limite por keyword em vez de global (`scraper.py:54,75`).

A ordem 1 a 5 entrega ~80% da robustez para o intervalo 10x. Os itens 7 e 11 decidem se 100x é possível.

## 8) Riscos legais, de ToS e anti-bot (objetivos)

- **ToS**: o tráfego usa a **API privada do app móvel** (Kwai Lite), anônima, com assinatura reproduzida por engenharia reversa e identidade de dispositivo emulada (`client.py:23-57`). Em geral, isso viola os Termos de Uso de plataformas desse tipo (acesso por meio não autorizado, contorno de mecanismos técnicos). Eu não li os ToS do Kwai nesta análise: isso é um ponto a validar com jurídico antes de uso comercial. A busca usa o endpoint web com UA de Chrome (`config.py:15-18`), o que também pode contrariar regras de scraping.
- **Contorno de proteção**: reproduzir `sig` e imitar o app é, para efeitos legais e de risco, contornar uma medida técnica de controle. Em alguns ordenamentos isso agrava a posição jurídica em comparação com scraping de HTML público. Em escala, a exposição cresce.
- **Dados pessoais (LGPD/GDPR)**: o conteúdo coletado inclui identificadores e nomes de usuários, textos e comentários de terceiros (`models.py`: autor, texto). Em volume isso é tratamento de dados pessoais: exige base legal, minimização, retenção e atendimento a pedidos de exclusão. O código não faz nada disso (sem pseudonimização, sem política de retenção).
- **Anti-bot**: identidade única e estática, IP único, delay constante (1,5 s fixo, padrão de tráfego regular), sem jitter. Fácil de detectar e bloquear. Em escala, a resposta de mercado são proxies residenciais e rotação, que elevam o custo e o risco legal (uso de IPs de terceiros).
- **Fragilidade técnica**: sal e versão do app fixos (`client.py:24-26`). Uma atualização do app/servidor pode inutilizar a coleta sem aviso. Não há detecção automática (ver gargalo 5).
- **Carga sobre terceiros**: acima de 10x, o volume pode caracterizar abuso de infraestrutura. O candidato escolheu delay conservador por padrão (1,5 s), o que é uma boa prática a preservar e a tornar adaptativa (reduzir com 429).
- **Recomendação**: para uso em produção, preferir canal oficial (API/parceria/licença de dados) se existir. Para pesquisa e prova de conceito, manter volume baixo, identificar o coletor quando possível, respeitar `robots.txt` no que for web e manter registro de finalidade e retenção.

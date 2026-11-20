# Análise de escala — PR #5 (Lucas7721, Kwai, Nível 1, DDD/hexagonal)

Informativo: o Nível 1 não exige escala. Caminhos relativos a `src/`.

## 1) Veredito

- **Não escala como está.** É uma CLI síncrona, de processo único, de uma execução por vez. Serve para dezenas ou centenas de itens por execução, não para milhares de keywords/perfis por dia nem para milhões de registros.
- **Escala com ressalvas depois de poucas mudanças localizadas.** O que ajuda de verdade são os use cases como geradores, as portas de API pequenas e a separação dos clientes HTTP. Os bloqueadores estão na infraestrutura: rate limiter em processo, identidade de dispositivo fixa, sem proxy, sem resume, sem fila e sem estado.
- **O teto real é externo.** Ele vem da identidade falsa única de app Android, com `sig` por sal extraído, e do anti-bot do Kwai, e aparece antes de qualquer limite de CPU ou memória. Isso é risco de ToS (ver 8).

## 2) Como funciona hoje

- **Execução.** Totalmente síncrona. `httpx.Client` (bloqueante) com `time.sleep` no limiter. Não há `async`, threads de trabalho nem `asyncio` em lugar nenhum (grep).
- **Orquestração.** Cada comando da CLI chama `_run_exports` (`entrypoints/cli/export_commands.py:183-206`). Ele cria `Settings()`, cria a pasta da execução, monta o container (`infrastructure/container/container.py:421-441`) e consome o gerador de resultados em série.
- **Três rotas.**
  - Busca: API web `www.kwai.com`, POST JSON, `pcursor` numérico usado como offset de 50 em 50 (`web/adapter.py:57-60`, `SEARCH_PAGE_SIZE=50`). Fim da busca = uma página sem posts novos (`use_cases/search_posts.py:541-553`).
  - Perfil: API móvel. `getInfo` resolve o handle, depois `feed/profile` pagina por `pcursor` opaco, 30 por página (`mobile/adapter.py:135`).
  - Comentários: API móvel, raízes de 50 em 50 e sublista de 100 em 100 (`mobile/adapter.py:131-133`).
- **Assinatura.** `MD5(k=v ordenados + SIG_SALT)` (`mobile/signature.py:57-61`). O sal `382700b563f4` está em `mobile/app_identity.py:17`, válido só para `appver 10.3.20.539600`. A própria docstring diz que outra versão dá `result:50`.
- **Identidade.** Um único dispositivo fictício, hardcoded: `vid/did/egid/mod` (`mobile/adapter.py:143-171`). O UA da busca web é fixo, vindo de `config/settings.py`.
- **Persistência.** `exports/<handle>/<UTC>-<uuid8>/` com `posts.json` e `comments/<id>.json` ou `comments-replies/<id>.json`. Escrita atômica com tmp + rename (`entrypoints/cli/export_files.py:63-89`).
- **Estado.** Não há estado global mutável. Os `set` de dedup e de cursores vivem dentro de cada chamada. O único estado compartilhado é o `RateLimiter`, dentro da instância do cliente.

## 3) Gargalos e bloqueadores

| # | Evidência | Impacto em escala |
|---|---|---|
| B1 | `infrastructure/kwai/ratelimit.py:22-35`: `threading.Lock` + `time.sleep`, uma instância por cliente (`web/client.py:32`, `mobile/client.py:212`). | O pacing existe só dentro de um processo. N workers = N vezes a taxa e N vezes o risco de bloqueio. Não é compartilhável entre processos nem máquinas. É global por cliente, não por host nem por IP. O cliente móvel usa um limiter para os 3 gateways (`client.py:269-270`). |
| B2 | `mobile/client.py:269-289`: a escada percorre 3 hosts em qualquer falha, inclusive 429/403/WAF, cada um com `rate.wait()`. Em volta, `http_utils.py:156-161` repete até 1+`max_retries`, com `wait_exponential(0.5..8s)`. | Sem `Retry-After`, sem jitter (grep). Uma falha vira até 12 requisições em ~40 s ao mesmo backend. Sob bloqueio isso agrava o ban. O backoff máximo de 8 s é curto para 429 real. Sem jitter, N workers sincronizam e geram rajadas (thundering herd). |
| B3 | `mobile/app_identity.py:12-19` e `mobile/adapter.py:143-171`: sal, `appver`, `vid/egid/did` constantes. | Todos os workers parecem o mesmo aparelho. Rate limit ou ban por device derruba todo mundo junto. Não há rotação de identidade. A API trava em uma versão do app, e quando o Kwai a aposenta o coletor para por inteiro. |
| B4 | Sem proxy: `settings.py` não tem campo de proxy e o `httpx.Client` só honra `HTTP_PROXY` do ambiente (um proxy global por processo). | Sem pool de IPs, sem rotação, sem sticky-session por perfil. Um IP só aguenta algumas dezenas de milhares de requisições por dia antes de risco de bloqueio. |
| B5 | Sem detecção de bloqueio. `is_transient_failure` (`http_utils.py:60-70`) trata HTML/WAF e 429 como transitório e repete. | Captcha, shadow-ban ou resposta vazia disfarçada de sucesso (200 com lista vazia) não são distinguidos de "fim da paginação". `search_posts.py:550` encerra a keyword na primeira página sem novos. Isso vira perda silenciosa de dados. Não há circuit breaker. |
| B6 | Sem resume nem checkpoint. A `posts.json` do perfil só é escrita depois de paginar tudo (`collect_user_posts.py:79-88`, `export_commands.py:199-201`). O `.partial.json` só sai quando a exceção é `KwaiCollectorError`. | `kill -9`, OOM ou queda da máquina perdem a execução inteira. Cursor não é persistido. Cada rerun começa do zero numa pasta nova (`export_files.py:57`). |
| B7 | Memória: tudo acumula antes de gravar. Posts em `list` (`collect_user_posts.py:79`). Raízes de comentários em `list` mais o set de dedup (`collect_comment_versions.py:359-363`). `expand_replies` guarda tudo de novo em `expanded` (linha 375). `write_export` faz `json.dumps` do total numa string (`export_files.py:80`). | Para um post com milhões de comentários, o pico passa de 3x o tamanho dos dados. Cada dataclass em Python pesa centenas de bytes a ~1 KB. Estimativa: 1M comentários ficam em ~1-3 GB. O formato é um array JSON, não JSONL, então não dá para anexar nem fazer streaming. |
| B8 | Sem paralelismo: o modelo de comentários é 1 requisição por post em série (`collect_profile_bundle.py:140-148`) e, com `--with-comments-replies`, 1 por raiz com respostas. | O throughput de comentários é por requisição, não por volume (ver 5). |
| B9 | Sem persistência de estado entre execuções: sem banco, sem índice de "já coletado", sem merge. O dedup só vale dentro de uma execução (`domain/services/identity.py`). Cada execução grava de novo os mesmos posts. | Coleta incremental ou recorrente (mesmo perfil todo dia) gera duplicatas entre pastas e consumo redundante de quota. |
| B10 | Sem agendamento, sem fila, sem métricas. Só `logging` em texto. O log do `httpx` em INFO imprime a URL inteira com o fingerprint (ver relatório prévio). | Sem observabilidade, não há como saber taxa de 429, latência ou progresso por perfil. |
| B11 | Layout de saída: uma pasta nova por execução, um arquivo por post de comentários (`export_files.py:77-78`). | Milhões de arquivos pequenos: estresse de inodes e listagem lenta. Em objeto remoto (S3) isso viraria um PUT por post. |
| B12 | Entrada: um handle ou uma URL por execução de CLI (`export_commands.py:232-293`). Sem leitura de lote. | Milhares de perfis exigem um wrapper externo, sem controle compartilhado de taxa (B1). |

## 4) O que já ajuda a escalar

- **Use cases como geradores** (`collect_profile_bundle.py:125-148`, `iter_pages` em `application/pagination.py`). Cada unidade (posts, comentários de um post) é entregue e gravada assim que fica pronta. Mantém memória baixa no nível de perfil e comentários de poucos itens. Esse é o único ponto de streaming real, e ele é bom.
- **Portas pequenas e estáveis** (`ISearchApiPort`, `IProfileApiPort`, `ICommentApiPort`, `IClockPort`). Trocar o transporte (httpx síncrono por async, ou por um pool com proxy) mexe só nos clients e adapters. O domínio e os use cases não mudam.
- **Domínio puro** (política de cursor, dedup, ordenação), testável e sem I/O. Isso permite mover o dedup para um banco sem reescrever a regra.
- **Parciais com erro explícito** (`CollectionResult.failed`, `reraise_with_partial`). Um worker de fila pode reaproveitar o resultado parcial e a causa.
- **Detecção de laço de cursor** (`RepeatedCursorError`) e dedup por `id` ou `url`.
- **Escrita atômica** de arquivos (tmp + rename) e nomes seguros. É a base para um resume por arquivo.
- **Container como composition root** (`container.py`). Dá para criar um container por worker.
- **Config por ambiente** (`KWAI_REQUEST_DELAY`, `KWAI_MAX_RETRIES`), útil em contêineres.
- **Sem estado global**: não há singleton escondido. Processos independentes funcionam sem interferir entre si, só não coordenam a taxa.

### Quanto da hexagonal habilita escala e quanto é cerimônia

- **Habilita (cerca de um terço).** As portas de saída das APIs, o domínio puro e os use cases baseados em geradores. Isso torna possível trocar o HTTP síncrono por async ou por um pool de proxies, e consumir comandos de uma fila, sem tocar na regra.
- **Cerimônia para escala.**
  - As quatro portas de entrada (`application/ports/use_case_ports.py`) têm uma implementação cada e não ajudam a rodar workers.
  - `IClockPort` é só `datetime.now()`.
  - Os value objects e DTOs de comando não resolvem nenhum problema de escala.
- **O que faltaria e não existe nenhuma porta para isso.**
  - Porta de saída/armazenamento: a escrita em disco está dentro do CLI (`export_files.py`) e não atrás de uma porta. Trocar por banco, S3 ou Kafka exige mover essa lógica, não só plugar um adapter.
  - Porta de rate limiter ou de política de acesso: o `RateLimiter` é concreto e instanciado dentro dos clients, então não dá para injetar um limiter distribuído sem editar os clients.
  - Porta de repositório de estado (cursor, "já coletado").
  - Porta de proxy ou identidade.
  - Async: as portas são síncronas (`def`), então um adapter async exige mudar a assinatura das portas e dos use cases.
- **Conclusão honesta.** A arquitetura reduz o custo de trocar o HTTP e o formato de saída, mas as três peças que mais importam para escalar (limiter, estado/sink, identidade) estão no lado errado da fronteira. Por isso o ganho real é moderado.

## 5) Medições

Rede real, perfil público `parkourcity`, sem credenciais, 28 requisições no total. `KWAI_REQUEST_DELAY=0.3` para não demorar. O resultado limita-se à latência e ao custo por requisição; com o padrão de 1,5 s a taxa é bem menor. Script em `(ambiente de avaliação)`. Máquina de desenvolvimento, uma execução por caso; é indicativo, não benchmark.

| Caso | Requisições | Tempo total | Latência média/req | Bytes/req | Pico RSS |
|---|---|---|---|---|---|
| `profile -l 90` (getInfo + 3 páginas de 30) | 4 | 2,1 s | 0,51 s | ~106 KB | 51 MB |
| `search -k parkour -l 150` (3 de 50 + 1) | 4 | 4,6 s | 1,14 s | ~228 KB | 52 MB |
| `comments` de um post (15 raízes) | 1 | 0,5 s | 0,43 s | ~16 KB | 49 MB |
| `profile -l 15 --with-comments-replies` | 18 | 7,8 s | 0,43 s | ~16 KB | 50 MB |

- O último caso gerou 136 registros de comentários e respostas em 15 posts: ~17 registros/s, ~2,3 req/s. Esse número é com delay de 0,3 s, não com o padrão.
- A busca devolveu 184 posts únicos em 4 requisições. Perfil: 90 posts em 4. A página de busca é a mais pesada (228 KB) e a mais lenta.
- Pico de memória de ~50 MB é a linha de base do interpretador mais bibliotecas. O volume dessas coletas é pequeno demais para mostrar crescimento. A projeção de B7 é por leitura de código, não medida.
- Não consegui medir 429, bloqueio nem posts virais, porque o perfil público tem posts com poucos comentários (máximo de 23).

### Throughput por instância com o padrão (1,5 s entre requisições)

- O intervalo é início a início, no limiter único por cliente. Isso dá ~0,67 req/s por cliente, e os dois clientes (web e móvel) têm limiters independentes. Na prática uma execução de CLI usa um deles por vez.
- Por dia, uma instância faz cerca de **57 mil requisições** (0,67 × 86 400).
  - Busca: 50 posts/req, no máximo ~2,9 milhões de posts/dia (teórico). Na prática, bem menos por causa da profundidade da busca e do dedup. Eu não testei até onde o offset vai.
  - Perfil: 30 posts/req, ~1,7 milhão de posts/dia (teórico).
  - Comentários: 1 req por post com poucos comentários. Dá ~57 mil posts/dia por instância. Com respostas, soma 1 req por raiz que as declara, então pode cair por um fator 3-10.
  - Contando getInfo + paginação + retries, uma "keyword/perfil" completa costuma custar de 3 a 10 requisições. Isso dá da ordem de **6 mil a 20 mil unidades de keyword ou perfil por dia por instância**, se nenhum bloqueio ocorrer.
- Bloqueio, não CPU, limita antes. A CPU é ociosa (E/S bloqueante com sleep).

## 6) Estimativa 10x / 100x / 1000x

Base: uma instância ≈ 57 mil req/dia, ~1-10 mil perfis/keywords/dia, ~50 MB.

- **10x (dezenas de milhares de keywords/perfis por dia, ~10 processos ou máquinas).**
  - Primeiro quebra o pacing (B1): 10 processos geram ~7 req/s sem coordenação, com a mesma identidade (B3) e provavelmente o mesmo IP (B4).
  - Em seguida vem o bloqueio (B5). Sem detecção, o coletor devolve listas vazias e as grava como se fossem completas.
  - Depois, a falta de resume (B6): quedas e bloqueios apagam horas de trabalho.
  - Contornável com: limiter central, pool de proxies, checkpoint por cursor. Esforço médio.
- **100x (centenas de milhares/dia, milhões de posts/comentários).**
  - Quebra a persistência: milhões de arquivos JSON e pastas por execução (B11), sem índice, sem dedup entre execuções (B9).
  - Quebra a memória em posts de muitos comentários (B7) e a falta de agendamento e de fila (B12).
  - O sal e o `appver` fixos viram ponto único de falha (B3): uma mudança no app para toda a frota.
  - Exige fila + banco + workers async, e uma rotação de identidade real (que nesse ponto é problema jurídico, não técnico).
- **1000x (dezenas de milhões de requisições/dia).**
  - Inviável com este desenho e, provavelmente, com a abordagem de engenharia reversa de API móvel anônima. Exigiria acordo comercial/API oficial ou um provedor de dados.
  - O Kwai detectaria o padrão (device fixo, UA fixo, sal extraído) muito antes. A arquitetura não é o limitador; o acesso é.

## 7) Roadmap priorizado

Esforço: P = pequeno (horas), M = médio (dias), G = grande (semanas).

1. **P** Gravar posts e comentários incrementalmente (JSONL, um append por página) e persistir o último `pcursor` por perfil/keyword num arquivo de checkpoint. Habilita resume e elimina B6 e a maior parte de B7. O gerador `iter_pages` já entrega página a página, então a mudança fica no sink.
2. **P** Tratar `429` e `Retry-After`, adicionar jitter ao backoff (`http_utils.py:156-161`), limitar a escada de gateways a 1 volta por rodada e não repeti-la em 429/403. Parar a coleta (circuit breaker) depois de N falhas seguidas.
3. **P** Distinguir "lista vazia legítima" de bloqueio: marcar resposta vazia suspeita, registrar contadores de status e o motivo de parada por keyword/perfil.
4. **M** Extrair uma porta de sink (`IExportSink`) e uma de `IRateLimiter`. Implementar limiter compartilhado (Redis token bucket, por host e por identidade) e sink para banco/objeto.
5. **M** Camada de identidade e proxy: pool de proxies com sticky por perfil, identidades de dispositivo rotativas, UA por identidade. Sal e `appver` ficam em config versionada, com health-check periódico que sinaliza o `result:50`.
6. **M** Fila de trabalho (Redis/RabbitMQ/SQS): uma tarefa = um perfil, uma keyword ou um post (e sua página de cursor), idempotente. Workers sem estado, um container por worker (o container atual já permite).
7. **M** Banco de estado: tabela de posts/comentários por `id` (upsert) e tabela de cursores/última coleta. Dá dedup entre execuções e coleta incremental (parar ao chegar no que já se tem).
8. **M** Observabilidade: métricas (req/s, latência, 429/403, itens/s, parciais), logs estruturados sem URLs com fingerprint, alertas de queda de taxa.
9. **G** Cliente async (`httpx.AsyncClient`) com concorrência limitada por host e por identidade. Exige tornar as portas `async`. Só vale depois de 4 e 5, senão só aumenta o bloqueio.
10. **G** Agendador (cron/Airflow/Temporal) para recoleta periódica e reprocessamento de falhas. Mover o acesso para uma fonte contratada se o volume pedir 1000x.

## 8) Riscos legais, ToS e anti-bot

- **Engenharia reversa do app.** O coletor assina requisições com um sal extraído do app Android e se passa por um dispositivo Android (`mobile/adapter.py:143-171`). Isso é contornar mecanismo técnico do serviço. Provavelmente viola os Termos de Uso do Kwai, e em algumas jurisdições pode se enquadrar como acesso não autorizado ou violação de medida de proteção. Em escala, o risco jurídico cresce junto com o volume.
- **Falsificação de identidade.** `vid/did/egid` são de um aparelho fictício. Rotacionar identidades para fugir de limite (item 5) piora o enquadramento, porque passa a ser evasão deliberada de controle de acesso.
- **Dados pessoais.** Comentários, handles e ids numéricos são dados pessoais (LGPD/GDPR). Coletar em massa e guardar sem base legal, sem política de retenção e sem canal de exclusão cria passivo. O desenho atual não tem nenhum controle de retenção ou anonimização.
- **Anti-bot.** Os sinais que o Kwai pode usar: identidade de dispositivo constante, taxa regular de 1 requisição a cada 1,5 s (padrão previsível, sem jitter), um IP, UA fixo, ausência de cookies e dos tokens `__NS_sig3`/`__NStokensig` (excluídos de propósito, `signature.py:312`). Os endpoints anônimos podem ganhar exigência de token a qualquer momento.
- **Fragilidade de contrato.** O `appver` pinado e a API não documentada podem mudar sem aviso. Para um produto, é risco operacional e contratual.
- **Recomendação.** Para escala comercial, usar API oficial, parceria ou provedor de dados licenciado. Manter este coletor como prova de conceito de baixo volume.

# Análise de escala – PR #1 (RaphaZY, Kwai Nível 0)

Escopo: código em `sistema/` do checkout `(ambiente de avaliação)`. Análise informativa; o Nível 0 não exige escala. Caminhos abaixo são relativos a `sistema/`.

## 1) Veredito
**Não escala como está; escala com ressalvas só para posts/busca (rotas web), e não escala para comentários.**
Busca e posts de usuário são HTTP simples e sem estado, então dá para paralelizar por fora (vários processos/IPs). Comentários dependem de um único emulador Java/unidbg serializado, de identidade de dispositivo fixa e de um runtime Windows-only (não validado em Linux), e isso é o teto duro.
É uma boa prova de conceito (módulos limpos, 180 testes offline), mas sem concorrência, retry, proxy, checkpoint nem fila.

## 2) Como funciona hoje
- CLI síncrona, single-thread, single-process (`kwai_collector/__main__.py:229-243`). Sem `asyncio`, threads ou pool em nenhum arquivo (grep: nenhuma ocorrência). O único `sleep` é o de 1 s antes de cada download de mídia (`midia.py:400`).
- Busca: loop de páginas de 10 itens via POST com `curl_cffi` `impersonate="chrome131"`, paginando por offset no corpo (`web_client.py:84-160`, `config.py:293`).
- Usuário: 1 chamada de perfil + páginas de 20 por cursor opaco (`web_client.py:213-264`).
- Comentários: rota mobile `/rest/o/comment/list/v2` com `sig` (MD5 reimplementado em Python, `kwai_sign.py`) e `__NS_sig3` obtido por HTTP de um serviço local Java/unidbg em 127.0.0.1:8765 (`sig3.py:345-363`, `mobile_client.py:160-173`).
- Saída: uma pasta por vídeo com `postagem.json`, `comentarios.json` e `media/` (`__main__.py:5-14, 70-82`).

## 3) Gargalos e bloqueadores
| # | Gargalo | Evidência | Impacto |
|---|---|---|---|
| 1 | **Assinador único e serializado.** `synchronized (signLock)` em volta da chamada nativa; `HttpServer` com `setExecutor(null)` (thread única). O próprio README admite: o emulador não é thread-safe e as chamadas esperam na fila. | `server/src/com/kwai/sig3/KwaiSign.java:157-161, 228`; `server/README.md` | Teto de throughput de comentários = 1 assinatura por vez por processo JVM. Escalar exige N JVMs. |
| 2 | **Health check em toda assinatura**: `assinar()` faz `GET /health` e depois `POST /sign`, ou seja, 2 round-trips locais por requisição de comentários. | `sig3.py:352, 357` | Overhead pequeno, mas desnecessário; também sem sessão HTTP reutilizada (`requests.get/post` soltos, sem `Session`). |
| 3 | **Portabilidade/empacotamento.** `server/` tem 143 MB (JDK 8 Windows em `server/jdk8`, rootfs Android, APK, libs ARM) mais `server.zip` de 70 MB duplicado. Inicia via `run.bat`; a mensagem de erro sugere `cmd.exe /c` (`sig3.py:355`). Sem Dockerfile. Não consegui subir em Linux (relatório prévio: falha no Unicorn). | `server/`, `sig3.py:355` | Rodar N instâncias em containers/VMs Linux exige trabalho de portabilidade não feito. Custo por instância: JVM + emulador ARM64 (memória não medida, ver seção 5). |
| 4 | **Latência/CPU do emulador não medidas e provavelmente altas.** unidbg interpreta ARM64 via Unicorn; cada assinatura é CPU-bound e serial. Inicialização leva "alguns segundos" (`server/README.md`). | `KwaiSign.java:44-67` | Não consegui medir (serviço não sobe em Linux). Ordem de grandeza típica de unidbg: dezenas a centenas de ms/assinatura, o que é suposição, não medição. |
| 5 | **Identidade de dispositivo fixa e compartilhada.** `did`, `vid`, `egid`, `zid`, `session_id`, `app_id`, `user_id`, `gaid` têm valor padrão hardcoded em `config.py` e `.env.example`; `llsid` e `netScore` são literais no código. Sem rotação ou pool de identidades. | `config.py:326-335`, `.env.example`, `mobile_client.py:91,96` | Toda a coleta de comentários aparece ao Kwai como UM aparelho. Em volume vira o primeiro alvo de bloqueio/rate limit. Também é identidade reaproveitada de uma captura real (risco ToS, seção 8). |
| 6 | **Sem rate limit, retry, backoff, proxy.** Qualquer status != 200 vira `NetworkError` imediato; sem tratamento de 429/403, sem `Retry-After`, sem proxies (grep: nenhuma ocorrência de retry/backoff/proxy). Falha de rede em perfil/busca aborta o comando inteiro (`web_client.py:205-206`); em comentários da busca/usuário é "melhor esforço" (`__main__.py:46-55`) e perde dados em silêncio relativo. | `web_client.py:194-210`, `mobile_client.py:270-271` | Primeiro 429/captcha derruba o job. Não há como distinguir "sem conteúdo" de "bloqueado": `result != 1` sempre vira `break` (`web_client.py:135-138, 242-243`; `mobile_client.py:278-281`), então bloqueio parece fim de dados (perda silenciosa). |
| 7 | **Sem checkpoint/resume/idempotência.** Cada execução reescreve tudo; não pula vídeos já coletados, não guarda cursor, não há manifesto. A pasta de saída é fixa `out/` relativo ao cwd (`__main__.py:61, 92`). Execução interrompida a meio perde a lista (usuario só grava `usuario.json` ao final: `__main__.py:97`) e recomeça do zero. | `__main__.py:58-138` | Jobs longos (perfis com milhares de posts) não são recuperáveis. |
| 8 | **Persistência em muitos arquivos pequenos.** 1 pasta + 1-2 JSON (+ 2 mídias) por vídeo, JSON com `indent=2` (`__main__.py:34-37`). 1 milhão de posts = 1-2 milhões de arquivos/inodes, sem sharding por diretório (todos os vídeos da keyword ou do usuário em uma só pasta). Sem DB, Parquet/JSONL nem object storage. | `__main__.py:70-78` | Degrada o filesystem na casa de centenas de milhares de arquivos por diretório; difícil consultar/deduplicar; sem escrita atômica (arquivo parcial em crash). |
| 9 | **Memória: acumula tudo em lista** (`results`, `postagens`) até o fim e só então grava (`web_client.py:97, 231`; `mobile_client.py:253`). Por si só leve, pois só guarda campos mapeados (~35 MB RSS medido), mas sem streaming; limites altos (milhares de posts/comentários por job) crescem linearmente. Não é o gargalo. | ver seção 5 | Baixo até ~10^5 itens por job. |
| 10 | **Mídia**: download sequencial, sem retomada, sem checagem de existência, sem verificação de tamanho, com `sleep(1)` fixo por arquivo (`midia.py:383-405`). Mínimo ~2 s por vídeo só de espera; vídeo baixa com `requests` simples (sem impersonation, UA fixo) do CDN. | `midia.py` | ~30 vídeos/min/instância no máximo, e armazenamento ilimitado. Tráfego de CDN é o mais visível para detecção. |
| 11 | **Paginação/limites.** Busca por offset (`pcursor += page_size`) em páginas de 10 itens (`web_client.py:158`, `config.py:293`); a relevância da busca determina profundidade, e não há evidência no código de profundidade máxima nem de reprodutibilidade entre execuções. Comentários: 20/página, cursor opaco (`config.py:294`). Busca não traz `autor.id` (limitação documentada). Perfil: pagina até `no_more`. | `web_client.py:84-160, 230-264` | Cobertura limitada e não determinística em keywords amplas; dados de autor incompletos para a busca. |
| 12 | **Sub-comentários: N+1.** 1 chamada assinada extra por comentário com resposta, e `except NetworkError: pass` engole erros (`mobile_client.py:292-297`). Em cima do gargalo #1 isso multiplica o custo. | `mobile_client.py:192-236, 292` | Posts virais ficam inviáveis com `--com-subcomentarios`. |
| 13 | **Sem fila/agendamento/observabilidade.** Sem logger (só `print`), sem métricas, sem contagem de erros por tipo, sem IDs de job, sem scheduler. Sem entrada em lote (uma keyword/usuário por invocação, sem lista de alvos). | `__main__.py` (apenas `print` com `[ok]/[aviso]/[erro]`) | Operação a milhares de alvos/dia exigiria wrapper externo (cron/Airflow) e parse de stdout. |
| 14 | **Fragilidade (engenharia reversa/impersonation).** Dependência de: APK e `libkwsgmain.so` de uma versão específica (appver 10.3.20.539600), `REAL_APPID`/hash de assinatura hardcoded (`KwaiSign.java:39-41`), constantes de derivação de chave do `sig` (`kwai_sign.py:92-95`), endpoint mobile `api1-us.kwai-pro.com`, e impersonation `chrome131` de TLS. Qualquer rotação de versão/chave quebra tudo e exige nova engenharia reversa (não é config). | `kwai_sign.py`, `KwaiSign.java`, `config.py:289,311` | Risco de manutenção alto e contínuo; um cliente "Chrome 131" ficará velho. |
| 15 | **Testabilidade em volume.** Os 180 testes são offline com mocks (bom), mas não há teste de carga, de concorrência, nem contrato contra a API real. `.env` lido na importação de `config.py` (estado global de módulo, `DEVICE` dict global), o que dificulta rodar múltiplas identidades no mesmo processo. | `config.py:263-270, 308`; `mobile_client.py:70` | Para multi-identidade seria preciso refatorar `config` para objeto injetável. |

Estado global/local: `config.DEVICE`, `_deriver` global em `kwai_sign.py:79-80`, `.env` local, `out/` relativo ao cwd. Nada compartilhado entre máquinas, então várias máquinas rodam, mas todas usariam a mesma identidade e o mesmo `out/` local.

## 4) O que já ajuda a escalar
- Rotas web (busca/perfil/feed) **sem assinatura nem login**, stateless, idempotentes de leitura: paralelizáveis por processo com facilidade.
- `curl_cffi` com impersonation de TLS (reduz bloqueio por fingerprint) e timeout configurável (`config.py:292`).
- Separação em módulos (`web_client`, `mobile_client`, `sig3`, `schemas`, `midia`) e schema normalizado (`schemas.py`): fácil trocar a camada de transporte/persistência.
- Dedup por `seen_ids` dentro de um job (`web_client.py:100, 232`) e cursor opaco respeitado.
- Falha de mídia/comentário não derruba a coleta (`midia.py:404`, `__main__.py:46-55`).
- Parâmetros (page size, URLs, timeouts, UA) já vêm de env.
- `sig` reimplementado em Python (sem JVM); só o `__NS_sig3`(ambiente de avaliação)`ambiente de avaliação/m/bench.py`.
- Feed de perfil, 8 páginas sequenciais de 20 posts: 0,59 a 1,06 s por página (média ~0,80 s). Todas devolveram 19-20 itens.
- `carregar_perfil(limit=100)` (1 chamada de perfil + 5 páginas): **100 posts em 4,85 s, cerca de 1.240 posts/min**.
- `buscar_por_palavra_chave("parkour", limit=60)` (6 páginas de 10): **60 em 5,85 s, cerca de 615 posts/min**.
- 15 chamadas seguidas de perfil: 7,5 s total, média 0,50 s, máximo 0,55 s. Sem 429, sem degradação, sem captcha (amostra pequena, não prova ausência de limite).
- Memória: pico de RSS ~35 MB para esses jobs (só metadados).
- Não medido: assinatura `__NS_sig3`, comentários e download de mídia. O serviço Java não sobe em Linux (tentativa prévia falhou no Unicorn) e `server/jdk8` é Windows. Os números de comentários abaixo são estimativas, não medições.

## 6) Estimativa por fator (base: 1 instância)
Base medida (web, sem mídia, sem comentários): ~600-1.200 posts/min por processo, ~0,8-1 s por requisição, latência dominada por rede. 1 instância/dia no limite teórico: 0,9 a 1,7 milhão de posts/dia, **se o Kwai não limitar o IP** (hipótese não testada). Perfis: com 20 posts/página e ~1 s/página, ~1.200 posts/min.
Comentários (estimativa): 20 por página, 1 assinatura serializada + 1 request. Assumindo 0,3-1,5 s por página no total, ~800-4.000 comentários/min por JVM (suposição, não medido).

| Fator | O que quebra primeiro |
|---|---|
| **1x** (dezenas de keywords/perfis/dia) | Nada crítico. Funciona em cron com `out/` local. Falta retry: uma falha transitória aborta o job. |
| **10x** (centenas de alvos, ~10^5 posts/dia) | (a) Sem retry/backoff, falhas esporádicas e bloqueios silenciosos (`result != 1`→`break`) viram dados faltando sem alerta. (b) Reescrita completa sem resume. (c) Mídia a 1 s/arquivo. Comentários: o assinador único ainda aguenta, mas já em poucas horas por dia de CPU serial. Rate limit por IP provavelmente aparece. |
| **100x** (milhares de alvos, ~10^6 posts/dia) | (a) IP único bloqueado: precisa de pool de proxies residenciais. (b) Identidade única de dispositivo (did/egid/zid fixos) queimada para comentários. (c) Assinador serializado: precisa N JVMs, e hoje só Windows. (d) 1-2 milhões de arquivos/dia no filesystem local, sem DB. (e) Sem fila/orquestração/observabilidade: não há como saber o que falhou. |
| **1000x** (~10^7-10^8 posts/dia, várias máquinas) | Arquitetura inviável sem reescrita: precisa de fila distribuída, armazenamento colunar/objeto, pool de identidades gerenciado, gestão de proxies, detecção de bloqueio, monitoração de quebra de assinatura. O custo de manter o `sig`/`sig3` contra rotação do app vira trabalho contínuo de equipe. Também é aqui que o risco legal/ToS e de bloqueio ativo deixam de ser teórico. |

## 7) Roadmap (priorizado; P = pequeno <1-2 dias, M = ~1 semana, G = semanas)
1. **(P)** Retry com backoff exponencial e jitter, tratamento explícito de 429/403/5xx, distinção "fim de dados" vs "bloqueio" (hoje `result != 1` → `break`). `Session` HTTP reutilizada; remover o `/health` por assinatura.
2. **(P)** Checkpoint/resume: gravar cursor e IDs coletados, pular vídeos existentes, escrita atômica (tmp + rename), `--out` configurável.
3. **(M)** Camada de execução concorrente para as rotas web: `asyncio`/`curl_cffi.AsyncSession` ou pool de workers, com limitador de taxa por host/IP e entrada em lote (lista de keywords/handles).
4. **(M)** Persistência escalável: JSONL/Parquet por lote ou DB (Postgres/ClickHouse) + object storage para mídia, chave por `photo_id` (upsert/idempotência); sharding de diretórios se mantiver arquivos.
5. **(M)** Proxies rotativos e refatorar `config.DEVICE` para objeto injetável; pool de identidades (did/egid/zid/session) por worker, com quarentena de identidade bloqueada.
6. **(M-G)** Containerizar o assinador: Dockerfile Linux (JRE + unidbg), validar o Unicorn em Linux, pool de N instâncias atrás de balanceador, remover o JDK/APK/`server.zip` do repositório (artefatos separados), métricas de latência/fila. Medir de fato throughput por JVM.
7. **(M)** Fila + scheduler (Redis/RabbitMQ/Celery/Temporal ou Airflow), workers stateless, DLQ, logging estruturado, métricas (Prometheus) e alertas de taxa de erro/queda de itens por página.
8. **(G)** Mitigar a fragilidade: testes de contrato diários contra a API real, versionamento de appver/assinatura, plano de re-engenharia reversa quando o app rotacionar, e avaliar se a rota web basta para comentários (evitaria todo o assinador).
9. **(P)** Mídia: download paralelo com retomada/verificação, só quando necessário, e rate limit separado para CDN.

## 8) Riscos legais, ToS e anti-bot (objetivos)
- **ToS**: coleta automatizada do kwai.com e da API mobile, em geral, é vedada pelos termos de plataformas desse tipo (não verifiquei o texto atual dos termos do Kwai; confirmar com o jurídico). A rota mobile exige **burlar um mecanismo de proteção** (assinatura `__NS_sig3`/`sig` via engenharia reversa do APK e emulação da lib nativa), o que é o ponto de maior risco: pode ser tratado como contorno de medida técnica de proteção (DMCA 1201/Lei de software/legislações equivalentes) e não apenas violação contratual. A rota web é o caminho de menor risco.
- **Uso de APK e `libkwsgmain.so` do Kwai redistribuídos no repositório**: possível violação de direitos autorais do titular (cópia/redistribuição de binários proprietários, 143 MB em `server/` e `server.zip`).
- **Identidade simulada**: reuso de identificadores de dispositivo/usuário capturados (`user_id`, `gaid`, `egid`, `zid`) e impersonation de Chrome/app. Se o `user_id` padrão (`DEVICE_USER_ID`) for de uma conta/pessoa real, é dado pessoal embutido no repositório; confirmar a origem.
- **LGPD/privacidade**: os dados coletados incluem handle, id e texto de comentários de terceiros (dados pessoais). Em volume exige base legal, minimização, retenção e política de acesso; o coletor não tem nada disso.
- **Anti-bot**: o Kwai pode retaliar por IP, TLS fingerprint, identidade de dispositivo ou padrão de tráfego (taxa constante de ~1 req/s, 1 s fixo de espera na mídia, sempre os mesmos IDs). Não há detecção nem reação a bloqueio no código. A estabilidade depende de vetores que o fornecedor pode mudar a qualquer momento sem aviso.
- **Mídia**: baixar vídeos de terceiros e armazená-los em larga escala adiciona risco de direitos autorais além da coleta de metadados.

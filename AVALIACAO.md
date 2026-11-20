# Avaliação · Desafio Kwai · Nível 0 · RaphaZY

**PR:** #1 · **Branch:** `solution/kwai-nivel0-raphazy` · **Data:** 2026-11-20

| | |
|---|---|
| Nota base (critérios ponderados + bônus) | **67.00** (era 78,25 antes do ajuste de corretude) |
| Penalização por uso de IA (−25% da nota base) | não se aplica |
| **Nota final** | **67.00 / 100** |

## Como a nota foi calculada
Método do `docs/avaliacao.md`: cada critério recebe nota 0–4 e a nota final é a soma de (peso × nota/4), mais o bônus. O nível escolhido é o contrato: avaliamos contra os requisitos do Nível 0. Foco da avaliação: solução, código escrito e README de instalação e execução.

---


## (a) Resumo
CLI Python (`python -m kwai_collector busca|usuario|comentarios`) em `sistema/`. Busca e posts de usuário usam rotas WEB públicas do kwai.com via `curl_cffi` (sem assinatura) e **funcionam de verdade** (testado contra o Kwai real). Comentários usam a rota mobile e exigem `sig` (MD5 reimplementado em Python) + `__NS_sig3`, gerado por um serviço local Java/unidbg embutido (`server/`, ~73 MB de JDK 8 Windows + libs + APK, mais um `server.zip` duplicado de 73 MB). O código é bem separado em módulos, há 180 testes offline (todos passam), amostras reais, `PESQUISA.md` extenso e PR bem descrito, com decisões e limitações honestas. Pontos fracos: o fluxo de comentários só está documentado para Windows (`cmd.exe /c server\run.bat`); não consegui subir o servidor no Linux, então comentários não foram verificados ao vivo. O README tem referências quebradas (`cd kwai-collector`, `TROUBLESHOOTING.md`, `requirements-dev.txt` inexistentes). `busca` não tem `--out` e não gera um JSON único, ao contrário do exemplo do enunciado. O campo `texto` sai com entidades HTML sem decodificar.

## (b) Evidência de execução
Ambiente: Linux, Python 3.12.3, sem Java. venv em `scratchpad/venvs/pr1`.

Instalação (README): `pip install -r requirements.txt` OK. `cp .env.example .env` OK. O README manda fazer `cd kwai-collector`, mas a pasta é `sistema/` (ambiguidade; o PR diz `cd sistema`).

- `python -m kwai_collector busca --keyword "parkour" --limit 5 --sem-comentarios` -> `[ok] 5 postagem(ns) salva(s) em out/parkour` (1,8 s). Gera `out/parkour/<id>/postagem.json` (5 pastas). Não existe flag `--out` e não há um arquivo único de lista.
  - Resultados reais: 2 de 5 têm texto sem relação com "parkour" (`@lcjxx306`, `texto: null`; `@comediano_01` `#KwaiChef2025 #cobertura #Comédia`). Isso vem da relevância da API, não é erro do código.
  - `autor.id` = null em todos os resultados da busca (o feed da busca não traz `user_id`). Está documentado como limitação do feed.
- `python -m kwai_collector usuario --user "@parkourcity" --limit 5` -> `[ok] 5 item(ns) salvo(s) em out/parkourcity/usuario.json` (1,4 s). Campos corretos: `autor.id` "150001214685137", datas ISO `2024-10-02T20:47:59Z`, engajamento numérico. O `texto` veio como `"GOSTOU? SEGUE PARA MAIS V&Iacute;DEOS! ..."` (entidade HTML não decodificada).
- `comentarios --url ".../@parkourcity/video/123" --out out/c.json` sem o serviço no ar -> `[erro] servico de assinatura __NS_sig3 nao esta respondendo em http://127.0.0.1:8765. Suba com: cmd.exe /c "server\run.bat --serve 8765"` (mensagem clara, sem traceback; porém o comando sugerido é Windows-only).
- `comentarios --url "lixo"` -> `[erro] nao foi possivel extrair o photo_id da URL 'lixo' ...` (OK).
- Tentativa de alternativa: baixei um JDK 8 Linux (Adoptium, via `install-jdk`) e rodei `java -cp "classes:lib/*" com.kwai.sig3.KwaiSign --serve 8765`. Falhou em `Unicorn.<clinit>` com `Couldn't load library unicorn_java`. Com `-Djava.library.path` apontando para `natives/linux_64` do `unicorn-1.0.15.jar`: `UnsatisfiedLinkError ... undefined symbol: helper_div_i32`. Conclusão: o serviço de assinatura não sobe no Linux x86_64 com as dependências incluídas. Isso é uma limitação do pacote do candidato (README só cobre Windows), não da rede. **Comentários não foram verificados ao vivo.** Pela amostra `samples/comentarios.json` (11 itens reais, schema ok) e pelos testes com fakes, o caminho parece ter funcionado no ambiente do autor.
- `pytest -q` (após `pip install pytest`; o README manda `requirements-dev.txt`, que não existe, mas `pytest>=8` está no `requirements.txt`) -> **180 passed in 0.47s**.

Validação contra `docs/schemas.md`:
- `Postagem`: todos os campos obrigatórios presentes (`url`, `engajamento`, `coletado_em`), datas ISO-8601 Z, campos desconhecidos como null (`autor.id` na busca, `texto` quando "..."). Extra `midia` é permitido.
- `Comentario` (amostra): `postagem_url`, `texto`, `coletado_em` presentes; `autor.usuario` é o nome de exibição ("Angélyca Rodrigues"), não o @handle; extra `respondendo_a`.
- Engajamento ausente vira `None`, não `0` (correto conforme schemas).

Segredos: nenhum token/cookie de conta encontrado. `.env.example` e `config.py` trazem um "fingerprint de dispositivo" fictício/capturado (`did`, `egid`, `zid`, `user_id` de convidado, `gaid`). Não são credenciais de conta, e o candidato explica isso, mas o `user_id` e o `gaid` parecem identificadores reais de um emulador. Risco baixo; não é eliminatório. `.env` está no `.gitignore`.

## (c) Tabela de critérios
| Critério | Peso | Nota (0-4) | Justificativa |
|---|---|---|---|
| Corretude das 3 funcionalidades | 45% | **2** (ajustada de 3: comentários não executam no Linux) | Busca e usuário funcionam no Kwai real, paginam e deduplicam. Comentários tem implementação completa (paginação por cursor, sub-comentários, melhor esforço), amostra real e testes, mas dependem de um serviço Java só validado em Windows e não consegui rodá-lo. Descontos: `busca` sem `--out` e sem JSON único (desvio do contrato de CLI do enunciado); entidades HTML no texto; `limit=50` fixo para comentários na busca. **Ajuste da avaliação:** a funcionalidade 3 (comentários) não executa em Linux x86_64: o servidor de assinatura Java/unidbg falha ao carregar a lib nativa do unicorn, e o README só documenta Windows (`cmd.exe`, `.bat`). Uma das três funcionalidades obrigatórias não roda em ambiente comum de desenvolvimento/servidor, então a corretude fica em 2 (funciona no caminho feliz, com limitação de plataforma). |
| Qualidade de código | 25% | 3 | Módulos coesos (CLI, config, schemas, clients, errors), nomes claros, docstrings úteis, hierarquia de erros e mensagens amigáveis. Descontos: duplicação em headers/POST (`buscar_por_palavra_chave` reimplementa `_headers_web`/`_post_json`), duplicação do bloco de comentários/mídia em `cmd_busca` e `cmd_usuario`, código morto, `except Exception` amplo, referências obsoletas (ver (e)). |
| Aderência aos schemas | 15% | 3 | Obrigatórios e formatos corretos, null honesto, extras permitidos. Descontos: `autor.id` sempre null na busca, `texto` com `&Iacute;`, `autor.usuario` do comentário é nome de exibição, não handle. |
| Documentação | 15% | 2 | `PESQUISA.md` e a descrição do PR são excelentes (decisões, trade-offs, desvio da sugestão do enunciado, limitações). Mas o README de instalação/execução tem falhas: `cd kwai-collector` incorreto, link para `TROUBLESHOOTING.md` e `requirements-dev.txt` inexistentes, "nota sobre .gitignore acima" que não existe, instruções de comentários só para Windows (`cmd.exe`, `.bat`) sem alternativa Linux/Mac, estrutura de código cita `server/jdk8` etc. Um usuário Linux não consegue rodar comentários seguindo o README. |
| **Subtotal** | | | 22,50 + 18,75 + 11,25 + 7,50 = **60,00** |
| Bônus (até +10) | | **+7** | Paginação real e testada nas 3 funcionalidades (+3); suíte de 180 testes pytest offline, bem organizada (+3); atraso configurável só no download de mídia, nenhum tratamento real de rate limit/retry/backoff nas chamadas à API (+1). Extras fora de escopo (perfil, mídia, sub-comentários) não pontuam. |

## (d) Pontos fortes
- Escolha pragmática: rotas web públicas para busca/usuário, sem assinatura, e justificativa documentada (inclusive o desvio da sugestão do enunciado).
- Honestidade técnica no PR e no README: 3995 de 4557 posts coletáveis, teto de busca não medido, sem restart automático do serviço.
- Tratamento de erros: `CollectorError` e subclasses, `main()` captura tudo com mensagem, sem traceback. URL inválida e serviço fora do ar foram verificados.
- Datas/ids/campos nulos tratados com cuidado (`ms_timestamp_to_iso`, `_texto_legivel`, `None` em vez de 0).
- Paginação com deduplicação e critério de parada claro (`no_more`, sem itens novos).
- Config toda via `.env` com `.env.example`; 180 testes verdes; amostras reais para as 3 funcionalidades.

## (e) Problemas no código e sugestões
1. `kwai_collector/web_client.py:89-95` vs `:184-191`: `buscar_por_palavra_chave` monta headers e faz `curl_requests.post` + tratamento de erro à mão (linhas 89-133), duplicando `_headers_web` e `_post_json` definidos mais abaixo. Sugestão: usar `_post_json` na busca (e mover os helpers para o topo), removendo ~40 linhas.
2. `web_client.py:267-269` `postagens_do_usuario` ("mantido para compatibilidade") e `errors.py:564` `EmptyResultError`: código morto, nunca usado. Remover.
3. `__main__.py:89-135` (`cmd_usuario`) e `:60-80` (`cmd_busca`): o mesmo bloco "gravar postagem.json + comentários melhor esforço + baixar mídia" aparece duas vezes. Extrair `_salvar_postagem(postagem, pasta_raiz, args)`.
4. `__main__.py:57-60`: `cmd_busca` usa `Path("out")` fixo e não aceita `--out`; o enunciado mostra `busca ... --out out/busca.json`. Sugestão: aceitar `--out` e gravar a lista JSON única (a árvore por vídeo pode ficar como opcional).
5. `__main__.py:73`: `limit=50` fixo para comentários na busca, sem opção na CLI. Adicionar `--comentarios-limit` como já existe em `usuario`.
6. Mensagens de aviso em stdout: `__main__.py:99-103` imprime `[aviso]` sem `file=sys.stderr` (inconsistente com os demais avisos).
7. `web_client.py:56-58` `_texto_legivel`: não decodifica entidades HTML (`V&Iacute;DEOS` saiu assim na coleta real). Aplicar `html.unescape(caption)`.
8. `mobile_client.py:296-297`: `except NetworkError: pass` engole a falha de sub-comentários sem avisar ("melhor esforço" silencioso). Emitir `[aviso]` em stderr.
9. `mobile_client.py:91` `"llsid": "4888814799695302308"` hardcoded e números mágicos (`netScore`, `ds`, `kwai_tiny_type`) fora do `.env`, apesar do README afirmar "Nada fica hardcoded". Mover para constante nomeada com comentário ou ajustar o README. `_montar_params` e `_montar_params_sublist` repetem ~25 chaves; extrair `_params_base()`.
10. `config.py:7,432`: comentário obsoleto "ver apk/tools/unidbg" (caminho de outro repositório). `kwai_sign.py:~10` e `PESQUISA.md` citam `kwai-collector/` e documentos (`assinatura-*.md`) que não estão no checkout.
11. `web_client.py:124`, `:203`, `:208` e `mobile_client.py:208`: `except Exception` amplo envolvendo `resp.json()`/post; trocar por `curl_requests.RequestException`/`ValueError`.
12. Sem tratamento de rate limit (HTTP 429/retry/backoff/pausa entre páginas) nas chamadas à API e sem verificação do tamanho de `limit` (`--limit 0` ou negativo devolve lista vazia sem aviso).
13. `sistema/server.zip` (73 MB) duplica o conteúdo de `server/` já versionado; isso infla o repositório. Manter só um (ou usar release/LFS). (Por pedido do avaliador, o JDK/binários em si não foram penalizados.)

## (f) Melhorias de documentação
- Corrigir `cd kwai-collector` para `cd sistema` e remover/ajustar referências inexistentes: `TROUBLESHOOTING.md`, `requirements-dev.txt`, "nota sobre `.gitignore` acima", "se a pasta não existe peça a cópia separadamente".
- Dar instruções para Linux/macOS (ex.: `java -cp "classes:lib/*" com.kwai.sig3.KwaiSign --serve 8765` com um JDK 8 local) e dizer claramente que `comentarios` hoje só foi validado em Windows. No Linux x86_64 o unicorn nativo empacotado não carrega.
- Mostrar no README um exemplo completo de `busca` com saída, e esclarecer que a saída é por pasta e não um JSON único (ou adicionar `--out`).
- Documentar `autor.id` null na busca e o `autor.usuario` de comentário ser nome de exibição na seção de campos nulos (o PR pede documentar o motivo de null).
- Explicar rapidamente a que expira/quebra: dependência de impersonation `chrome131` e de endpoints não oficiais, que podem mudar.

## (g) Nota base final
Corretude 2/4 x 45% = 22,50
Qualidade 3/4 x 25% = 18,75
Schemas 3/4 x 15% = 11,25
Documentação 2/4 x 15% = 7,50
Subtotal = 60,00
Bônus = +7
**Nota base final = 60,00 + 7 (bônus) = 67,00 / 100**

Ajuste: comentários não executam no Linux (unicorn nativo não carrega) e a documentação cobre só Windows. A corretude foi rebaixada de 3 para 2, o que leva a nota base de 78,25 para 67,00. Para recuperar os pontos: documentar e testar a execução em Linux/macOS (ou oferecer um caminho sem JVM/emulador) e corrigir a `README` conforme a seção (f).

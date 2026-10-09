# Pesquisa e explicação do sistema: `kwai_collector`

Este documento explica **por que** o `kwai_collector` foi construído do jeito que foi:
quais rotas do Kwai cada funcionalidade usa, por quê, e o que foi preciso descobrir/reverter
de engenharia reversa para chegar lá. É o resumo de uma pesquisa bem mais
longa, os documentos detalhados (`assinatura-sig-libcore.md`, `assinatura-nativa-sig3-sig4.md`,
`assinatura-comment-list-v2.md`, `rota-comment-list-v2.md`, etc.).

## Resumo executivo

O Kwai protege a API do **app mobile** com três mecanismos de assinatura por requisição:
`sig`, `__NS_sig3` e `__NS_sig4`. As rotas do **site** (kwai.com) são bem mais abertas,
várias não exigem nenhuma assinatura. A tabela abaixo resume o que cada funcionalidade do
nível 0 usa e por quê:

| Funcionalidade | Rota escolhida | Precisa de assinatura? | Por quê |
|---|---|---|---|
| Busca por palavra-chave | **Web** (`kwai.com`) | Não | Endpoint público do site já devolve tudo que o schema `Postagem` pede, sem login/sig3. Ver seção 4. |
| Postagens de um usuário | **Web** (`kwai.com`) | Não | `/rest/o/w/pc/feed/profile`, pública e paginada por cursor. Ver seção 5. |
| Comentários de uma postagem | **Mobile** (API do app) | Sim — `sig` **e** `__NS_sig3` | O site só expõe comentários via a mesma API mobile por baixo dos panos (route `/pc/getComments/list`) e, nos nossos testes, retorna resultado vazio sem um fluxo de "visitante" válido; a rota mobile `/rest/o/comment/list/v2` é a que de fato pagina e devolve o conteúdo completo. Ver seção 6. |

**Desvio deliberado em relação à sugestão original**: o enunciado do nível 0 supunha que tanto
a busca por palavra-chave quanto os comentários precisariam da rota mobile (com `__NS_sig3`).
Durante a implementação, encontramos e validamos um endpoint **web** público e funcional para
busca (`/rest/o/w/pwa/v2/search/word/outer`), que não exige nenhuma assinatura. Como ele já
entrega tudo que o schema pede (link, texto, engajamento) com muito menos fragilidade que a
rota mobile (sem precisar manter o serviço de sig3 no ar), optamos por usá-lo em vez de forçar
a busca pela rota mobile. Documentamos isso aqui para transparência, mas é uma mudança de
abordagem, não uma limitação.

---

## 1. Por que a API mobile é difícil: os três mecanismos de assinatura

Toda requisição sensível do app Android do Kwai carrega até três parâmetros de assinatura,
calculados por uma cadeia de bibliotecas nativas (`.so`) carregadas via JNI:

- **`sig`** (corpo da requisição, MD5): calculado por `libcore.so` (`CPU.getClock`). **Resolvido
  por completo** via engenharia reversa estática com Ghidra — é um MD5 do corpo canônico mais uma
  chave de 16 bytes derivada por uma cifra customizada cujas constantes estão hardcoded no
  binário (sem segredo de sessão). Reimplementado em Python puro em `kwai_collector/kwai_sign.py`
  (vendorizado dentro deste pacote, com os 3 arquivos binários de constantes em
  `kwai_collector/asm/`, para que `kwai-collector/` não dependa de nada fora de si mesma).
  Detalhes completos no repositório de pesquisa: `assinatura-sig-libcore.md`.

- **`__NS_sig3`** (também chamado de `atlasSign`): calculado por `libkwsgmain.so`, parte do SDK
  **KSecurity/聚安全 (SecurityGuard)**, o mesmo usado por vários apps do grupo Alibaba/Kuaishou.
  Diferente do `sig`, aqui não existe um atalho estático — o dispatcher nativo
  (`JNICLibrary.doCommandNative`) usa *control-flow flattening* pesado (o próprio Ghidra desiste
  de decompilar a função) e as libs trocam a permissão de memória da página de código em tempo de
  execução, o que quebra até instrumentação dinâmica convencional (Frida `Interceptor`/`Stalker`).
  **Resolvido não decifrando o algoritmo, mas reproduzindo sua execução**: ver seção 2.

- **`__NS_sig4`**: calculado por `libksxgs.so` (`GNative`). Formato de saída conhecido
  (`base64$TE_hex`), mas o algoritmo interno **não foi decifrado**. Boa notícia prática: nos
  testes reais desta sessão, pelo menos para o endpoint de comentários (`/rest/o/comment/list/v2`),
  o servidor aceitou a requisição **sem `__NS_sig4` nenhum** — então o `kwai-collector` não o
  envia. Se no futuro algum endpoint passar a exigi-lo, esse é o próximo algoritmo a atacar.

## 2. Como o `__NS_sig3` foi resolvido sem emulador Android

Depois de esgotar a engenharia reversa estática (Ghidra) e a instrumentação dinâmica (Frida),
ambas bloqueadas pelas proteções descritas acima, a virada veio de identificar que
`libkwsgmain.so` pertence a uma família de SDK já documentada publicamente (SecurityGuard), e que
outros pesquisadores já haviam usado o **unidbg** (`zhkl0228/unidbg`, um emulador ARM64 em Java)
para rodar bibliotecas semelhantes fora do Android.

A abordagem final:

1. **unidbg carrega a `.so` ARM64 real** (`libkwsgmain.so`, extraída do APK) num emulador Unicorn
   controlado inteiramente por código Java — sem QEMU, sem AVD, sem Android de verdade.
2. Construímos um ambiente Android **falso, mas suficiente**: uma classe `Context`/`Application`
   fake, um `PackageManager` fake que lê a assinatura (certificado) real do APK local, um
   `AssetManager` real (módulo `AndroidModule` já pronto no unidbg) e um sistema de arquivos
   virtual com o APK real posicionado exatamente no caminho que o código nativo tenta abrir
   diretamente (`getPackageCodePath()`).
3. Chamamos a função nativa `doCommandNative(cmd, args)` diretamente — a mesma função que o app
   real chama por baixo do `KSecurity.atlasSign()` — com os argumentos exatos (descobertos via
   hooks Frida ao vivo no device real, usados só para *validar* os argumentos, não para assinar
   em produção).
4. **Resultado**: o valor devolvido bate em formato com o `atlasSign()` real (24 bytes em hex) e,
   mais importante, **o servidor do Kuaishou aceitou uma requisição real assinada com esse valor**
   (`HTTP 200`, `result: 1`, comentários reais devolvidos).

Isso significa que o `__NS_sig3` é calculado **sem nenhum emulador Android rodando**, só um
processo Java comum (JVM + unidbg), que roda como um serviço local persistente
(`apk/tools/unidbg/run.bat --serve`). Essa é a peça que faltava para tornar `comentarios`
viável como uma funcionalidade de nível 0 de verdade, e não só uma simulação.

Detalhes completos (incluindo todos os bugs de ambiente contornados, JDK incompatível,
bibliotecas de sistema erradas, filesystem virtual, etc.) estão em `assinatura-nativa-sig3-sig4.md`
e na memória de longo prazo do projeto.

## 3. Limitações honestas do `__NS_sig3`

- O algoritmo **não foi decifrado**, não existe uma fórmula Python para `sig3`. O que existe é
  uma forma de **reproduzir fielmente** o cálculo nativo original.
- A saída é **não-determinística** (o algoritmo real embute um nonce interno), isso é esperado
  e bate com o comportamento observado no app real, não é um bug.
- O formato de wire do `__NS_sig3` (hex puro vs. `prefixo+base64(hex)`) **varia por versão do
  app/SDK**, o `kwai-collector` usa o formato hex puro, que é o que bateu com a versão da
  biblioteca usada aqui (`apk/libs-so/libkwsgmain.so`, do pacote `kwai.lite.video`/`com.kwai.prolite`).
- Os campos de índice 6/7 do array de argumentos de `doCommandNative` (um boolean e uma string)
  não têm significado totalmente mapeado, usamos a combinação que bateu com uma chamada real
  capturada (`false`, string vazia). Pode não ser universal para todo tipo de requisição.

## 4. Busca por palavra-chave (rota web)

Endpoint: `POST https://www.kwai.com/rest/o/w/pwa/v2/search/word/outer`

Descoberto incidentalmente numa captura de rede de uma página de vídeo (o site dispara essa
chamada para popular uma lista de "relacionados"), mas confirmado como um endpoint de busca real
e público ao testar com `searchWord` preenchido de verdade, retorna resultados relevantes, sem
necessidade de cookies, login ou qualquer assinatura. Cada item da resposta já traz `caption`,
`like_count`, `comment_count`, `view_count`, `forward_count`, `kwai_id` (usuário) e `photo_id_str`
(para montar o link), exatamente o que o schema `Postagem` pede.

Paginação: o servidor não devolve um cursor na resposta, mas aceita e respeita um `pcursor` de
entrada incrementado em passos de `count` (confirmado empiricamente: páginas sucessivas não têm
sobreposição de resultados). Sondagem com a palavra "filmes": 793 postagens únicas em 80 páginas
(count=10), sem sinal de teto — parada manual, porque cada página leva alguns segundos. O teto real
da busca não foi medido.

## 5. Postagens de um usuário (rota web: sem login)

Endpoint: `POST https://www.kwai.com/rest/o/w/pc/feed/profile` com corpo
`{"userId": "<handle>", "fromPage": "PC_PROFILE", "beforePage": "", "count": 20, "pcursor": <cursor>}`.

Achado a partir do bundle JS do próprio site (`app_bundle.js`, função `getPCProfileFeed`): a
página de perfil usa essa rota para o "carregar mais". Ela é pública (sem login, cookies ou
assinatura), devolve `feeds` no **mesmo formato de item** da busca e um campo `cursor` (token
opaco, na prática o timestamp do último item) que é reenviado como `pcursor` na página seguinte.
Testado contra um perfil real: 207 páginas, 3995 postagens únicas, até a resposta vir vazia.

Isso substitui a abordagem anterior (Playwright lendo `window.__NUXT__`), que só enxergava o lote
inicial de ~12 itens do SSR. **Playwright não é mais necessário.**

Observação: o perfil de teste declara `ownerCount.photo = 4557`, mas o feed paginado entregou 3995;
a diferença provavelmente são itens que o feed público omite (removidos/filtrados), não
investigado.

**Dados de perfil (`usuario --perfil`)**: `POST /rest/o/w/pwa/profile` (também público, `{"userId": handle}`) devolve uma
chave irmã `userProfile` com tudo que precisávamos para o schema `Perfil`: `profile.user_name`,
`profile.userText`/`user_text` (bio), `profile.verified`, `profile.headurl` (avatar), e
`ownerCount.fan`/`ownerCount.follow`/`ownerCount.photo` (seguidores/seguindo/total de postagens).
Veio "de graça" no mesmo carregamento de página já usado para as postagens, não precisou de uma
chamada extra.

**Achado sobre o campo `caption`**: para postagens sem legenda, esse feed (busca e perfil) traz o
literal `"..."` em vez de uma string vazia. Confirmamos (comparando com a extração de
`kwai_video_info.py` na página do próprio vídeo, que mostra a legenda real como string vazia
nesses casos) que isso é um placeholder visual do Kwai, não texto real, então `_texto_legivel()`
em `web_client.py` normaliza `"..."` para `None`, em vez de propagar um valor que pareceria uma
legenda de verdade mas não é.

## 6. Comentários de uma postagem (rota mobile: `sig` + `__NS_sig3`)

Endpoint: `POST https://api1-us.kwai-pro.com/rest/o/comment/list/v2` (mesma API usada pelo app
Android; o domínio `api1-us.kwai-pro.com` é um espelho/proxy já usado em capturas anteriores
deste projeto para esse mesmo endpoint).

Existe também uma rota web (`/rest/o/w/pc/getComments/list`) e uma rota mobile "lite"
(`/rest/o/lite/comment/list`, só `sig`, sem `sig3`) — ambas avaliadas e descartadas para esta
funcionalidade: a rota web, em testes anteriores deste projeto, devolveu respostas vazias sem um
fluxo de sessão de visitante totalmente resolvido; a rota "lite" tem um teto rígido de 20
comentários sem paginação. A rota `/v2` com `sig`+`sig3` é a única que pagina de verdade e
devolve o conteúdo completo, então é a usada aqui, e é exatamente o cenário que a pesquisa do
`__NS_sig3` (seção 2) foi feita para destravar.

Fluxo de uma chamada:
1. Extrai o `photoId` da URL da postagem (`.../video/<id>`).
2. Monta os parâmetros da requisição (fixos de dispositivo + `photoId`/`pcursor` específicos).
3. Calcula `sig` (MD5, `kwai_sign.compute_sig`).
4. Monta a string canônica de assinatura (`"POST&/rest/o/comment/list/v2&" + parâmetros
   ordenados (incluindo o sig) + "&" + nonce aleatório`) e manda para o serviço local de
   `__NS_sig3` (`apk/tools/unidbg`, via `kwai_collector.sig3`).
5. Envia a requisição completa; pagina seguindo o `pcursor` devolvido pela resposta.

### Sub-comentários (respostas encadeadas)

O `commentCount` que o app mostra na tela conta comentários principais **+** sub-comentários
(respostas diretas a um comentário, formando uma conversa encadeada), confirmado comparando a
soma real de `sub_comment_count` de todos os comentários principais de um vídeo de teste com o
`commentCount` da resposta. O v2 (seção acima) só pagina os comentários **principais**; cada um
que tem respostas vem com um campo `sub_comment_count > 0`, mas as respostas em si **não** vêm
inclusas nessa resposta na prática — mesmo a resposta trazendo um campo `subCommentsMap`, ele veio
sempre vazio (`{}`) em todos os nossos testes, mesmo para comentários com `sub_comment_count > 0`.
Uma captura antiga (de uma sessão de pesquisa anterior, com o app completo `com.kwai.video`, não o
Lite) mostrou esse mesmo campo **populado de verdade**, tentamos reproduzir isso imitando os
parâmetros daquela captura (incluindo trocar `appver`/`pkg` para os da mesma versão), mas a troca
de `pkg` quebrou a assinatura (nosso `sig3` está ancorado à identidade/certificado do APK
`kwai.lite.video` que carregamos no `server/`, anunciar um `pkg` diferente no request gera uma
inconsistência que o servidor rejeita com `result: 50`). Não investigamos mais a fundo o porquê do
`subCommentsMap` vir vazio para nós (pode ser algo ligado à versão do app, ao tamanho da thread,
ou a um parâmetro ainda não identificado) — ficou sem resposta definitiva.

**Resolvido por outro caminho**: o endpoint dedicado `POST /rest/o/comment/sublist` (documentado
estaticamente via smali em `rota-comment-list-v2.md`, mas nunca testado ao vivo em nenhuma sessão
anterior) busca as respostas de UM comentário principal especificado por `rootCommentId`. Testamos
direto contra o servidor real reaproveitando o MESMO pipeline de assinatura do v2 (`sig` +
`__NS_sig3`, só troca o `PATH` e os parâmetros da requisição), **funcionou de primeira**,
devolvendo as respostas reais de um comentário que sabíamos ter `sub_comment_count=2`, com
paginação por `pcursor` igual ao v2. Implementado em
`kwai_collector.mobile_client.sub_comentarios_de_comentario()`, exposto na CLI via
`--com-subcomentarios` (nos comandos `comentarios`, `usuario --comentarios` e `busca`). Cada
sub-comentário sai marcado com um campo extra `respondendo_a` (id do comentário principal), já que
o schema `Comentario` oficial não distingue comentário principal de resposta.

**Custo**: uma chamada HTTP extra por comentário principal que tiver resposta, em vídeos com
muitas conversas encadeadas isso pode multiplicar bastante o tempo de coleta, por isso é opt-in
(`--com-subcomentarios`), não o comportamento padrão.

### Pré-requisito operacional

O serviço de assinatura precisa estar rodando
(`kwai-collector\server\run.bat --serve 8765`) antes de usar o comando `comentarios`. Sem ele, a
CLI falha com uma mensagem clara (não um traceback), explicando como subir o serviço.

**Nota sobre `server/`**: essa pasta é uma cópia autocontida (biblioteca nativa + APK + bytecode
já compilado) do ambiente de pesquisa original. 

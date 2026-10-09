# kwai-collector

Coletor de dados públicos do Kwai (nível 0): busca por palavra-chave, postagens de um usuário e
comentários de uma postagem, com saída em JSON seguindo os [schemas](../docs/schemas.md).

Para o **porquê** de cada decisão técnica (quais rotas usamos, o que teve que ser reverso-engenheirado
para a funcionalidade de comentários funcionar, limitações conhecidas), veja [PESQUISA.md](PESQUISA.md).
Para erros conhecidos/esperados e como lidar com eles, veja [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

## Instalação

Requer Python 3.10+.

```bash
cd kwai-collector
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/Mac

pip install -r requirements.txt

copy .env.example .env          # Windows
# cp .env.example .env          # Linux/Mac
```

Nenhuma credencial é necessária nos dois primeiros comandos (`busca`, `usuario`) — são rotas
públicas do site. O comando `comentarios` depende de um serviço local auxiliar (ver abaixo).

## Pré-requisito do comando `comentarios`: serviço de assinatura `__NS_sig3`

A rota de comentários é uma rota do app mobile, protegida por uma assinatura nativa
(`__NS_sig3`) cujo algoritmo não foi decifrado matematicamente — em vez disso, este projeto
reproduz a execução real da biblioteca nativa do app (`libkwsgmain.so`) dentro de um emulador
ARM64 em Java (**unidbg**), sem precisar de nenhum emulador Android rodando. Veja
[PESQUISA.md](PESQUISA.md) para a explicação completa.

O servidor (um projeto Java/unidbg autocontido, já compilado) está em [`server/`](server/).

> Se você clonou este repositório e a pasta não existe,
> peça a cópia de `server/` separadamente 

Antes de rodar `python -m kwai_collector comentarios ...`, suba o servidor (fica rodando em
segundo plano, uma vez por sessão de trabalho):

```bash
cmd.exe /c "server\run.bat --serve 8765"
```

Confirme que está no ar:

```bash
curl http://127.0.0.1:8765/health   # deve responder "ok"
```

Se o serviço não estiver rodando, o comando `comentarios` falha com uma mensagem clara (não um
traceback) explicando como subir o serviço.

## Uso

### Estrutura de saída

Os comandos `busca` e `usuario` organizam a saída em pastas (dentro de `out/` por padrão), uma
por postagem coletada:

```
out/
└── <usuario-ou-palavra-chave>/
    ├── perfil.json           ← so para `usuario --perfil` (bio, seguidores, seguindo...)
    ├── usuario.json           ← so para `usuario`: lista com todas as postagens coletadas
    └── <id_do_video>/         ← uma pasta por postagem (so quando ha motivo: ver abaixo)
        ├── postagem.json
        ├── comentarios.json   ← melhor esforco, quando pedido
        └── media/
            ├── img/thumbnail.webp
            └── video/video.mp4
```

Em `busca`, a pasta por vídeo (com `postagem.json`) é sempre criada; em `usuario`, só quando você
pede `--comentarios` e/ou `--baixar-midia` (sem essas flags, a lista plana em `usuario.json` já
basta). Falha em baixar um comentário ou uma mídia específica nunca derruba o resto da coleta,
é avisada em stderr e a ferramenta segue pro próximo item ("melhor esforço").

### Busca por palavra-chave

```bash
python -m kwai_collector busca --keyword "eleicoes" --limit 50
python -m kwai_collector busca --keyword "eleicoes" --limit 50 --sem-comentarios
python -m kwai_collector busca --keyword "eleicoes" --limit 50 --baixar-midia
```

| Opção | Obrigatório | Padrão | Descrição |
|---|---|---|---|
| `--keyword` | sim | — | Palavra-chave a buscar |
| `--limit` | não | 50 | Quantidade máxima de postagens |
| `--sem-comentarios` | não | desligado | Não coleta comentários (por padrão, coleta por melhor esforço) |
| `--baixar-midia` | não | desligado | Baixa vídeo e thumbnail de cada postagem |
| `--com-subcomentarios` | não | desligado | Também busca as respostas de cada comentário (1 chamada extra por comentário com resposta) |

### Postagens (e perfil) de um usuário

```bash
python -m kwai_collector usuario --user "@perfil" --limit 50
python -m kwai_collector usuario --user "@perfil" --perfil
python -m kwai_collector usuario --user "@perfil" --comentarios --comentarios-limit 30
python -m kwai_collector usuario --user "@perfil" --baixar-midia
python -m kwai_collector usuario --user "https://www.kwai.com/@perfil" --out meu_arquivo.json
```

| Opção | Obrigatório | Padrão | Descrição |
|---|---|---|---|
| `--user` | sim | — | `@usuario`, `usuario` ou a URL do perfil |
| `--limit` | não | 50 | Quantidade máxima de postagens |
| `--out` | não | `out/<usuario>/usuario.json` | Caminho do JSON com a lista de postagens |
| `--perfil` | não | desligado | Também salva `out/<usuario>/perfil.json` |
| `--baixar-midia` | não | desligado | Baixa vídeo e thumbnail de cada postagem |
| `--comentarios` | não | desligado | Também coleta os comentários de cada postagem |
| `--comentarios-limit` | não | 50 | Máximo de comentários por postagem |
| `--com-subcomentarios` | não | desligado | Com `--comentarios`, também busca as respostas de cada comentário |

### Comentários de uma postagem

```bash
python -m kwai_collector comentarios --url "https://www.kwai.com/@perfil/video/XXXX" --out out/comentarios.json
python -m kwai_collector comentarios --url "https://www.kwai.com/@perfil/video/XXXX" --out out/c.json --com-subcomentarios
```

| Opção | Obrigatório | Padrão | Descrição |
|---|---|---|---|
| `--url` | sim | — | URL da postagem (precisa do serviço `__NS_sig3` no ar, ver acima) |
| `--limit` | não | 50 | Quantidade máxima de comentários **principais** (sub-comentários não contam pro limite) |
| `--out` | sim | — | Caminho do JSON de saída |
| `--com-subcomentarios` | não | desligado | Também busca as respostas de cada comentário principal (1 chamada extra por comentário com resposta, pode deixar a coleta bem mais lenta) |

Cada sub-comentário sai no mesmo JSON que os principais, marcado com um campo extra
`respondendo_a` (id do comentário principal ao qual responde; `null` para comentários
principais) — ver [PESQUISA.md](PESQUISA.md) para a explicação de como isso foi descoberto.

Em todos os comandos: se a coleta trouxer menos itens que o `--limit` pedido (ex.: a postagem não
tem tantos comentários, ou o perfil não tem tantas postagens disponíveis), a ferramenta salva o
que existir e avisa, nunca inventa dados para completar o número pedido.

### Configuração

Todas as opções configuráveis (endpoints, timeouts, tamanho de página, parâmetros de
"fingerprint de dispositivo" simulado) ficam em `.env` (veja `.env.example`). Nada fica
hardcoded no código-fonte, e nenhum dos valores é uma credencial de conta/usuário real.

### Amostras

A pasta [`samples/`](samples/) tem um exemplo de saída real (capturado durante o desenvolvimento)
para cada funcionalidade: `busca.json`, `usuario.json`, `comentarios.json` e `perfil.json`.

### Campos extras (além do schemas.md oficial)

- `Postagem.midia.{video_url,thumbnail_url}`: links diretos de CDN, usados por `--baixar-midia`.
  Schema extra, não exigido por [`../docs/schemas.md`](../docs/schemas.md), mas permitido por ele
  ("campos extras são bem-vindos").
- `Perfil` (`perfil.json`, comando `usuario --perfil`): schema novo, não faz parte do
  `schemas.md` original (que cobre só `Postagem`/`Comentario`) — campos: `usuario`, `id`, `nome`,
  `bio`, `verificado`, `avatar_url`, `seguidores`, `seguindo`, `total_postagens`, `url_perfil`,
  `coletado_em`.
- `Comentario.respondendo_a`: id do comentário principal, para sub-comentários coletados com
  `--com-subcomentarios` (`null` para comentários principais).

## Estrutura do código

```
kwai_collector/
├── __main__.py       # CLI (argparse): busca / usuario / comentarios
├── config.py          # le .env, nenhum valor hardcoded
├── schemas.py         # construtores dos dicts Postagem/Comentario
├── errors.py          # excecoes -> mensagens de erro amigaveis na CLI
├── web_client.py       # busca + usuario + perfil (rotas web, sem sig3, sem navegador)
├── mobile_client.py    # comentarios (rota mobile, sig + sig3)
├── midia.py             # download de video/thumbnail (--baixar-midia)
├── sig3.py              # cliente HTTP do servico local de __NS_sig3 (server/)
├── kwai_sign.py          # algoritmo do `sig` (MD5), vendorizado -- ver PESQUISA.md
└── asm/                   # 3 arquivos binarios pequenos usados por kwai_sign.py

server/                  # servico Java/unidbg que calcula __NS_sig3 (ver PESQUISA.md, secao 2)
├── run.bat               # sobe o servidor: run.bat --serve 8765
├── build.bat             # recompila src/KwaiSign.java (so necessario se voce editar a fonte)
├── jdk8/                  # JDK 8 embutido (o unidbg nao compila/roda em JDK 9+)
├── src/com/kwai/sig3/KwaiSign.java   # fonte do servidor
├── classes/, lib/         # bytecode + dependencias ja compiladas (prontas pra rodar)
├── libkwsgmain.so          # biblioteca nativa do app (extraida do APK) que o servidor emula
└── rootfs/                  # filesystem virtual com uma copia do APK, usado pela emulacao
```

`kwai-collector/` inteiro (incluindo `server/`) é **autocontido**: não depende de nenhum arquivo
fora desta pasta (nem o algoritmo do `sig`, nem o JDK, nem a lib nativa), pode ser copiada para
outra máquina e funcionar sozinha, desde que `server/` seja copiado junto (ver nota sobre
`.gitignore` acima).

## Testes

Suíte `pytest` em [`tests/`](tests/) — 100% offline: todo HTTP (rotas web, rotas mobile, serviço
`__NS_sig3`, download de mídia) é substituído por fakes, então **não precisa** de internet, do
servidor `server/` no ar nem de credenciais.

```bash
pip install -r requirements-dev.txt
python -m pytest                 # tudo
python -m pytest tests/clients   # so uma pasta (core | clients | cli)
```

- `tests/core/` — schemas e assinatura `sig` (`kwai_sign`)
- `tests/clients/` — `web_client`, `mobile_client`, `sig3`, `midia`
- `tests/cli/` — comandos `busca`, `usuario`, `comentarios` e `main`
- `tests/helpers.py` + `tests/conftest.py` — fakes de HTTP compartilhados (testados em `tests/test_helpers.py`)

## Limitações conhecidas (ver PESQUISA.md para detalhes e motivos)

- `busca`: pagina sem teto no código; o teto real do servidor não foi medido (testado: 790+ postagens
  únicas numa só palavra-chave). Cada página leva alguns segundos, então `--limit` alto demora.
- `usuario`: pagina pela rota pública `/rest/o/w/pc/feed/profile` até o fim do histórico do perfil
  (testado: ~4000 postagens num perfil). O feed público pode omitir alguns itens — num perfil de
  teste, 3995 de 4557 declarados em `total_postagens` — então o total coletado pode ser menor.
- `comentarios`: depende de um processo Java (`unidbg`) rodando localmente; sem ele, a
  funcionalidade fica indisponível (com mensagem de erro clara, não quebra silenciosamente).
- O formato de `__NS_sig3` usado (hex puro) foi validado contra a versão específica da
  biblioteca nativa incluída neste repositório; outra versão do app pode exigir um formato de
  saída diferente (ver PESQUISA.md, seção 3).

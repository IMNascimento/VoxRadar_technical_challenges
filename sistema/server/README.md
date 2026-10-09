# `server/` serviço local de assinatura `__NS_sig3`

Pequeno servidor HTTP (Java + [unidbg](https://github.com/zhkl0228/unidbg)) que calcula o
`__NS_sig3` das requisições da API mobile do Kwai. É usado **somente** pelo comando
`comentarios` (e por `usuario --comentarios` / `busca` quando coletam comentários). `busca` e
`usuario` (posts/perfil) usam rotas web e não passam por aqui.

Contexto da pesquisa: [`../PESQUISA.md`](../PESQUISA.md), seção 2.

## Como subir

```
server\run.bat --serve 8765
```

Sobe em `http://127.0.0.1:8765` (só localhost). A inicialização leva alguns segundos (carrega a
biblioteca nativa no emulador); quando aparecer
`[KwaiSign] servidor pronto em http://127.0.0.1:8765`, está no ar. O cliente Python fica em
[`../kwai_collector/sig3.py`](../kwai_collector/sig3.py) e usa a URL de `SIG3_SERVICE_URL` no `.env`.

Outros modos do mesmo `run.bat`:

| Comando | O que faz |
|---|---|
| `run.bat --serve [porta]` | Servidor HTTP (porta padrão 8765) |
| `run.bat <arquivo.txt>` | Assina o conteúdo do arquivo e imprime `SIG3_RESULT:<valor>` |
| `run.bat` (sem argumentos) | Assina duas vezes uma string de teste (mostra que o resultado varia) |

## API

| Rota | Entrada | Saída |
|---|---|---|
| `GET /health` | — | `200` com o texto `ok` |
| `POST /sign` | corpo = string a assinar, em UTF-8 (ex.: `POST&/rest/o/comment/list/v2&<params ordenados>&<nonce>`) | `200` + `__NS_sig3` em hex (48 caracteres nos testes); `204` se o nativo devolveu `null`; `500` + `error: ...` em exceção |

As chamadas são serializadas (um `synchronized`): o emulador não é thread-safe, então requisições
simultâneas esperam na fila. O valor **muda a cada chamada** mesmo com a mesma entrada (o
algoritmo embute um nonce interno), isso é esperado.

## Como funciona

1. `KwaiSign` cria um emulador ARM64 (unidbg + Unicorn) com um Android **falso, mas suficiente**:
   - `Context`/`Application` fake, `PackageManager` fake que lê o certificado do APK em `rootfs/`;
   - sistema de arquivos virtual (`rootfs/`) com o APK no caminho exato que o código nativo abre
     (`getPackageCodePath()`);
   - alguns símbolos de `libandroid.so` que faltavam no unidbg são stubados (`AAssetManager_openDir` etc.).
2. Carrega `libkwsgmain.so` (biblioteca nativa do SDK de segurança do app) e chama `JNI_OnLoad`.
3. `init()` chama `doCommandNative(0x28ac, ...)` uma vez (inicializa o ambiente do SDK).
4. Cada `POST /sign` chama `doCommandNative(0x28b2, ...)`, a mesma função que o app chama por
   baixo de `KSecurity.atlasSign()`, e devolve o resultado.

O algoritmo **não foi decifrado**; ele é *reproduzido* executando o código nativo original.

## Pastas e arquivos

```
server/
├── README.md             # este arquivo
├── run.bat               # sobe/roda o servico (usa o JDK embutido em jdk8/)
├── build.bat             # recompila src\...\KwaiSign.java (so se voce editar a fonte)
├── libkwsgmain.so        # biblioteca nativa ARM64 que o emulador executa (~744 KB)
├── src/com/kwai/sig3/
│   └── KwaiSign.java     # fonte: emulacao + servidor HTTP (/health, /sign)
├── classes/              # bytecode ja compilado + recursos do unidbg (~17 MB)
│   ├── com/kwai/sig3/    #   KwaiSign*.class (nosso codigo)
│   ├── com/github/...    #   classes do unidbg
│   ├── android/          #   libs de sistema Android (sdk19/sdk23) usadas pelo emulador
│   ├── net/fornwall/     #   parser de ELF usado pelo unidbg
│   └── log4j.properties
├── lib/                  # dependencias (jars) do unidbg (~18 MB)
├── jdk8/                 # JDK 8 embutido, reduzido (~102 MB), o unidbg nao roda em JDK 9+
└── rootfs/               # filesystem virtual do Android falso
    ├── data/app/.../kwai.lite.video-.../base.apk   # APK reduzido (~6 MB), ver abaixo
    ├── system/, tmp/     #   vazios (o emulador espera que existam)
    └── stdout.txt, stderr.txt   # vazios; o emulador cria
```

Tamanho total: ~143 MB (antes da reducao eram ~417 MB).

### Detalhes que importam

- **`libkwsgmain.so` vs. APK**: a `.so` é a do app **13.7.50** (`com.kwai.video`), enquanto o APK em
  `rootfs/` é o do **Kwai Lite 10.0.30** (`kwai.lite.video`). O código nativo usa o APK para ler
  o certificado de assinatura e abrir o próprio arquivo (não verifiquei se há outros usos); as requisições do coletor declaram
  `appver` 10.3.20 / `pkg` `kwai.lite.video`.
- **APK reduzido**: o original (172 MB, igual a `../../apk/Kwailite.apk`) teve `lib/`, `classes*.dex`
  e `res/` removidos (restaram ~6 MB). Tirar também `assets/` e a maior parte de `META-INF/` faz
  a assinatura voltar `null`, o nativo lê algo ali, então não corte.
- **`lib/` reduzido**: foram removidos os jars que o serviço não usa (`unidbg-dynarmic`,
  `unidbg-unicorn2`, `unidbg-hypervisor`, `unidbg-kvm`, `capstone`, `demumble`, `junit`,
  `hamcrest`). O `keystone` **precisa** ficar, sem ele o serviço não sobe. Cópia dos jars
  removidos: `../../server-removido-backup/lib/`.
- **Caminhos relativos**: `run.bat` faz `cd` para esta pasta; `libkwsgmain.so` e `rootfs/` são
  achados a partir dela. O nome longo da pasta do APK em `rootfs/` (`~~ZNQl4e...`) está fixo em
  `KwaiSign.java`; se renomear, edite a fonte e rode `build.bat`.

## Limitações e observações

- Nos testes, o servidor do Kwai **não conferiu o `__NS_sig3`** na rota `comment/list/v2` quando o
  `appver` declarado é ≤ 11.4: aceitou `sig3` real, aleatório e ausente (só o `sig` é conferido).
  Com `appver` ≥ 11.5 tudo foi recusado, mesmo com `sig3` real — causa não descoberta. Detalhes em
  `../PESQUISA.md`.
- O formato do `sig3` (hex puro) e os argumentos de `doCommandNative` foram validados contra esta
  versão da `.so`; outra versão pode exigir formato/argumentos diferentes.


# VoxRadar · Kwai Collector

> Coletor de dados públicos do Kwai desenvolvido como solução do **Desafio Técnico · Kwai** (Nível 0).
> Identificador do template: **A1_Radar**.

Implementa três funcionalidades de coleta, com saída em JSON aderente aos
[schemas do desafio](docs/schemas.md):

1. **Busca por palavra-chave** — postagens relacionadas a um termo.
2. **Postagens de um usuário** — todas as postagens de um perfil.
3. **Comentários de uma postagem** — comentários de um vídeo específico.

---

## 🚀 Instalação

### Requisitos

- **Python 3.10+**
- **pip** e **venv**
- **Chromium** (baixado automaticamente pelo Playwright)

### Passo a passo

```bash
# 1. Clone o repositório
git clone <url-do-seu-fork>
cd kwai

# 2. Crie e ative um ambiente virtual
python -m venv venv
source venv/bin/activate          # Linux/macOS
# ou: venv\Scripts\activate       # Windows

# 3. Instale as dependências
pip install -r requirements.txt

# 4. Baixe o Chromium usado pelo Playwright
playwright install chromium

# 5. Configure as variáveis de ambiente
cp .env.example .env
# edite o .env se necessário (os valores padrão já funcionam)
```

> ⚠️ O passo `playwright install chromium` é **obrigatório** — o `pip install`
> instala a biblioteca Python, mas não baixa o navegador. Sem ele, aparece o
> erro `playwright._impl._errors.Error: Executable doesn't exist`.

---

## 💻 Uso

### 1. Busca por palavra-chave

```bash
python -m kwai_collector busca --keyword "eleições" --limit 50 --out out/busca.json
```

| Argumento | Obrigatório | Padrão | Descrição |
|---|---|---|---|
| `--keyword` | ✅ | — | Palavra-chave a buscar |
| `--limit` | ❌ | 50 | Máximo de postagens |
| `--out` | ✅ | — | Caminho do JSON de saída |

### 2. Postagens de um usuário

```bash
python -m kwai_collector usuario --user "@EleicoesBrasil" --limit 100 --out out/usuario.json
```

| Argumento | Obrigatório | Padrão | Descrição |
|---|---|---|---|
| `--user` | ✅ | — | Nome de usuário (com ou sem `@`) |
| `--limit` | ❌ | 100 | Máximo de postagens |
| `--out` | ✅ | — | Caminho do JSON de saída |

### 3. Comentários de uma postagem

```bash
python -m kwai_collector comentarios --url "https://www.kwai.com/@perfil/video/XXX" --out out/comentarios.json
```

| Argumento | Obrigatório | Descrição |
|---|---|---|
| `--url` | ✅ | Link completo do vídeo |
| `--out` | ✅ | Caminho do JSON de saída |

---

## 📁 Estrutura do projeto

```
kwai/
├── kwai_collector.py          # código principal (CLI + coletores)
├── requirements.txt           # dependências Python
├── .env.example               # modelo de configuração
├── .env                       # config real (não versionada)
├── EXECUCAO.md                # este arquivo
├── README.md                  # índice do desafio
├── docs/                      # schemas e critérios (do template)
├── niveis/                    # especificações por nível (do template)
└── samples/                   # amostras de saída reais
    ├── busca_sample.json
    ├── usuario_sample.json
    └── comentarios_sample.json
```

---

## 🏗️ Decisões técnicas

### Por que Playwright e não `requests`/`httpx`?

O Kwai carrega conteúdo dinamicamente e assina requisições com headers
gerados por JavaScript. Reproduzir esse fluxo com `requests` exigiria
engenharia reversa dos tokens. O **Playwright** contorna isso naturalmente:
executa o JS real, mantém cookies de sessão e permite **interceptar XHR**
(`page.on("response", ...)`), combinando o melhor dos dois mundos.

### Estratégia por funcionalidade

| Funcionalidade | Estratégia |
|---|---|
| **busca** | Intercepta o XHR `.../search/word/outer` que a própria página dispara |
| **usuario** | Lê `window.__NUXT__` (SSR) para o primeiro lote + intercepta XHR de paginação |
| **comentarios** | Intercepta o XHR `.../getComments/list` |

### Configuração via `.env`

Todos os parâmetros ajustáveis (timeouts, `headless`, User-Agent) ficam no
`.env` — permite rodar em dev (`headless=false`) e em CI (`headless=true`)
sem alterar código.

### Aderência aos schemas

A montagem dos objetos `Postagem` e `Comentario` segue exatamente
[`docs/schemas.md`](docs/schemas.md):

- Datas em ISO-8601 UTC (`2026-09-11T14:30:00Z`)
- Campos ausentes viram `null` (nunca string `"null"`)
- Engajamento numérico com defaults `0`

---

## ⚠️ Limitação conhecida — coleta de comentários

A funcionalidade `comentarios` está **implementada corretamente** (identifica
o endpoint real, escuta a resposta XHR, monta o schema `Comentario`), mas o
Kwai **retorna erro para requisições anônimas**:

```json
{"result": 11, "error_msg": "请检查下网络连接是否正常"}
```

("Por favor verifique se a conexão de rede está normal")

### Diagnóstico

Investigação via Playwright mostrou que:

1. Os comentários **aparecem renderizados no DOM** (via SSR autenticado).
2. O endpoint `getComments/list` responde com `result: 11` para chamadas sem sessão.
3. Warm-up de cookies anônimos (visitando a home antes) **não resolve**.
4. O Kwai **exige sessão de usuário logado** para servir a lista de comentários.

### Trabalho futuro (fora do escopo do Nível 0)

1. **Login programático:** `context.add_cookies()` após autenticação manual,
   ou persistência via `storage_state`.
2. **Fallback via DOM:** parsear `page.query_selector_all()` como último
   recurso (frágil, mas funciona visualmente).

### Impacto

As funcionalidades `busca` e `usuario` operam **100%** e aderem ao schema.
Apenas `comentarios` fica limitada pelo bloqueio da plataforma.

Amostra do comportamento atual:
[`samples/comentarios_sample.json`](samples/comentarios_sample.json) (retorna `[]`).

---

## 🧪 Amostras de saída

Em [`samples/`](samples/), há uma execução real de cada funcionalidade:

| Arquivo | Descrição |
|---|---|
| [`samples/busca_sample.json`](samples/busca_sample.json) | 3 postagens do termo "eleições" |
| [`samples/usuario_sample.json`](samples/usuario_sample.json) | 3 postagens de `@EleicoesBrasil` |
| [`samples/comentarios_sample.json`](samples/comentarios_sample.json) | `[]` (limitação acima) |

Exemplo de item de `Postagem`:

```json
{
  "id": "5231925495560399313",
  "url": "https://www.kwai.com/@EleicoesBrasil/video/5231925495560399313",
  "autor": {
    "usuario": "Eleições 2022",
    "id": "150001298627113",
    "url_perfil": "https://www.kwai.com/@EleicoesBrasil"
  },
  "texto": "Arthur Lyra Lula tenta aprovação do bolsa família...",
  "data_publicacao": "2022-11-30T15:40:56Z",
  "engajamento": {
    "curtidas": 180,
    "comentarios": 17,
    "compartilhamentos": 22,
    "visualizacoes": 3947
  },
  "coletado_em": "2026-09-11T13:08:55Z"
}
```

---

## 📚 Referências

- [Especificação do desafio](README.md)
- [Schemas de saída](docs/schemas.md)
- [Critérios de avaliação](docs/avaliacao.md)
- [Requisitos do Nível 0](niveis/nivel-0.md)

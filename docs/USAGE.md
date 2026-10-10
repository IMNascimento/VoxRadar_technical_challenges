# Kwai Collector

CLI em Python para coletar dados públicos do Kwai, com paginação, controle de frequência e recuperação de falhas.

O projeto disponibiliza uma interface de linha de comando para:

- buscar postagens por palavra-chave;
- coletar postagens públicas de um perfil;
- coletar comentários principais de uma publicação;
- executar coletas agregadas de postagens e comentários.

A CLI grava os resultados em JSON.

---

## Requisitos

- Python 3.11+
- Poetry

Principais bibliotecas utilizadas:

- HTTPX
- Pydantic
- Pydantic Settings
- Pytest
- Ruff
- Mypy

---

## Instalação

Clone o repositório e acesse a pasta do projeto:

```bash
git clone <URL_DO_REPOSITORIO>
cd kwai-project
```

Instale as dependências:

```bash
poetry install
```

Verifique a CLI:

```bash
poetry run kwai-collector --help
```

O pacote inclui um assinador local para comentários paginados. Sem endpoint de assinatura configurado, coletas com `--max-comments 50` ou `todos` usam esse provider automaticamente, sem exigir `.env`, token ou serviço adicional.

Em 9 de outubro de 2026, os fluxos abaixo foram validados com o wheel isolado em outra pasta, sem variáveis `KWAI_*`, `.env`, cookies ou credenciais salvos:

| Validação | Resultado |
| --- | --- |
| [Postagem individual](validations/clone_sem_configuracao_2026-10-09.json) | 50 comentários com limite 50; 88 com `todos` |
| [Perfil e busca](validations/fluxos_sem_configuracao_2026-10-09.json) | 191 posts únicos de `henriqueejuliano`; 1.116 comentários em dez posts com `todos`; 1.475 em 50 posts de `sertanejo`, limitados a 50 por post; coletas sem erros por postagem |
| [Resultado final da busca com `todos`](validations/busca_sertanejo_todos_sem_configuracao_2026-10-09.json) | 8.893 comentários principais únicos nos 50 posts da amostra |

A listagem de 191 posts terminou por cursor repetido; não comprova esgotamento do histórico. Os critérios de conferência dos resultados estão na [documentação técnica](COLETA_COMENTARIOS.md#183-validação-sem-configuração).

---

## Uso

A aplicação possui quatro comandos principais:

```text
buscar
perfil
comentarios
coletar
```

### Buscar postagens

Busca postagens relacionadas a uma palavra-chave:

```powershell
poetry run kwai-collector buscar "sertanejo" --delay 2
```

Também é possível coletar os comentários das postagens encontradas:

```powershell
poetry run kwai-collector buscar "sertanejo" `
    --with-comments `
    --max-comments todos `
    --request-interval 2 `
    --delay 2
```

Para limitar a quantidade de comentários por postagem:

```powershell
poetry run kwai-collector buscar "sertanejo" `
    --with-comments `
    --max-comments 50 `
    --request-interval 2 `
    --delay 2
```

---

### Coletar postagens de um perfil

Coleta as postagens públicas disponíveis para um perfil:

```powershell
poetry run kwai-collector perfil "henriqueejuliano" --delay 2
```

O fluxo percorre as páginas disponíveis e remove postagens duplicadas. Encerra quando o cliente reconhece o término ou a repetição de um cursor.

---

### Coletar comentários

Recebe a URL de uma publicação e coleta seus comentários principais:

```powershell
poetry run kwai-collector comentarios `
    "https://www.kwai.com/@stanleyribeiro/video/5205466849377747864" `
    --max-comments 50 `
    --request-interval 2
```

Para seguir a paginação até o fim reconhecido:

```powershell
poetry run kwai-collector comentarios `
    "https://www.kwai.com/@stanleyribeiro/video/5205466849377747864" `
    --max-comments todos `
    --request-interval 2
```

`--max-comments` aceita um inteiro positivo ou:

```text
todos
```

O valor representa um limite máximo. Caso existam menos comentários disponíveis, a coleta termina com a quantidade encontrada.

A contagem considera comentários principais.

---

### Retomar uma coleta

Durante uma coleta paginada, o progresso pode ser salvo em checkpoint.

Caso a execução seja interrompida:

```powershell
poetry run kwai-collector comentarios `
    "https://www.kwai.com/@stanleyribeiro/video/5205466849377747864" `
    --max-comments todos `
    --request-interval 2 `
    --resume
```

A retomada preserva os comentários recebidos, aplica deduplicação e continua pelo cursor salvo.

Após uma conclusão bem-sucedida, o checkpoint correspondente é removido.

---

### Coleta agregada

O comando `coletar` reúne postagens e comentários em uma única execução:

```powershell
poetry run kwai-collector coletar `
    "henriqueejuliano" `
    --max-comments todos `
    --request-interval 2 `
    --delay 2
```

Esse fluxo processa até 10 postagens por execução.

Para coletar somente as postagens disponíveis de um perfil, utilize `perfil`.

---

## Fluxo de comentários

Coletas paginadas e retomadas utilizam a interface de preparação de requisições mobile.

O provider padrão calcula `sig` e `__NS_sig3` localmente para `POST /rest/o/comment/list/v2`, usando a implementação compatível com `kwai.lite.video` versão `10.3.20.540101`. O material fixo necessário está incluído no pacote e é verificado por SHA-256. Android, APK, Frida e serviços externos de assinatura não são necessários na execução.

A CLI compõe o assinador local e o injeta pelo protocolo `MobileRequestProvider`. A factory genérica também aceita providers alternativos; uma integração explicitamente configurada pode substituir o provider local.

Fluxo simplificado:

```text
CLI
 |
 v
MobileCommentProvider
 |
 v
MobileRequestProvider
 |
 v
LiveCommentClient
 |
 v
HTTP
 |
 v
Parser
 |
 v
JSON
```

---

## Configuração mobile opcional

O uso padrão dos comentários paginados funciona sem estas variáveis. Para substituir o assinador local por um serviço autorizado, configure:

```text
KWAI_MOBILE_AUTH_ENDPOINT
KWAI_MOBILE_AUTH_TOKEN
KWAI_MOBILE_AUTH_TIMEOUT
```

Exemplo:

```powershell
$env:KWAI_MOBILE_AUTH_ENDPOINT = "http://localhost:8000/prepare"
$env:KWAI_MOBILE_AUTH_TOKEN = "TOKEN_DO_SERVICO"
```

O token é utilizado somente para autenticar o coletor junto ao serviço configurado.

Se `KWAI_MOBILE_AUTH_ENDPOINT` estiver definido, a CLI usa essa configuração explícita. Sem esse endpoint, seleciona o assinador local.

Credenciais reais não devem ser versionadas.

---

## Campos adicionais

Campos adicionais podem ser configurados para query, body e headers:

```text
KWAI_MOBILE_QUERY_FIELDS
KWAI_MOBILE_BODY_FIELDS
KWAI_MOBILE_HEADER_FIELDS
```

Os valores devem ser objetos JSON compostos por strings.

Esses campos são opcionais. Os defaults de protocolo do provider local já correspondem à versão suportada; uma configuração incompatível de `pkg` ou `appver` é rejeitada. Não salvar controles variáveis de postagem/página nesses templates.

Exemplo:

```powershell
$env:KWAI_MOBILE_QUERY_FIELDS = '{"language":"pt-br"}'
$env:KWAI_MOBILE_BODY_FIELDS = '{"os":"android"}'
$env:KWAI_MOBILE_HEADER_FIELDS = '{"Accept":"application/json"}'
```

Use somente dados e integrações para os quais exista autorização de acesso.

---

## Rate limit e retry

O intervalo entre requisições pode ser controlado pela CLI:

```text
--request-interval 2
```

ou por configuração:

```text
KWAI_MOBILE_PAGE_DELAY
```

Falhas de rede e respostas HTTP configuradas como recuperáveis têm retry com backoff.

Variáveis disponíveis:

```text
KWAI_MAX_TENTATIVAS
KWAI_BACKOFF_BASE
```

Exemplo:

```powershell
$env:KWAI_MAX_TENTATIVAS = "3"
$env:KWAI_BACKOFF_BASE = "1"
```

O cliente mobile respeita um `Retry-After` válido antes da próxima chamada.

---

## Saídas

Os arquivos são armazenados por padrão em:

```text
samples/
```

Exemplos:

```text
samples/busca_sertanejo.json
samples/busca_sertanejo_comentarios.json
samples/<usuario>_posts.json
samples/<usuario>_comentarios.json
samples/<photo_id>_comentarios.json
```

Durante uma coleta paginada também pode existir temporariamente:

```text
samples/<photo_id>_comentarios.coleta.json
```

Esse arquivo representa o checkpoint da coleta.

Dados coletados em `samples/`, JSONs de comentários, checkpoints e backups não entram no commit de entrega. Os artefatos de validação versionáveis são relatórios estatísticos sem textos de comentários ou credenciais e fixtures de teste revisadas.

---

## Estrutura do projeto

```text
kwai-project/
|
|-- kwai_collector/
|   |-- clients/
|   |-- models/
|   |-- parsers/
|   |-- providers/
|   |-- security/
|   |-- cli.py
|   |-- cli_builders.py
|   |-- cli_collect.py
|   |-- cli_commands.py
|   |-- cli_comments.py
|   |-- cli_parsers.py
|   |-- cli_utils.py
|   |-- config.py
|   `-- keyword_comment_collection.py
|
|-- tests/
|-- samples/
|-- docs/
|-- .env.example
|-- .gitignore
|-- README.md
|-- poetry.lock
`-- pyproject.toml
```

---

## Arquitetura

O projeto separa as principais responsabilidades da aplicação.

### CLI

Responsável por:

- interpretação dos argumentos;
- validação de entrada;
- orquestração dos comandos;
- mensagens e códigos de retorno.

### Clients

Responsáveis pela comunicação HTTP e obtenção dos dados brutos.

### Providers

Concentram abstrações relacionadas à coleta, preparação de requisições, rate limit e checkpoints.

### Parsers

Transformam as respostas recebidas em estruturas utilizadas pela aplicação.

### Models

Representam e validam os dados normalizados.

O ponto de composição da CLI escolhe a factory local e injeta a implementação pelo protocolo `MobileRequestProvider`. A interface da factory genérica permanece disponível para testes e integrações alternativas. Os testes do provider padrão e das assinaturas verificam essa composição e os vetores de referência; o material empacotado tem sua integridade conferida por SHA-256.

Pacote, versão e User-Agent derivam das constantes do signer; os componentes compartilham a rota do endpoint. A composição preserva serviços explicitamente injetados mesmo quando sua avaliação booleana é falsa, com teste de regressão. Os algoritmos e o material binário foram preservados.

---

## Exemplo de postagem normalizada

```json
{
  "id": null,
  "url": "https://www.kwai.com/@usuario/video/123",
  "autor": {
    "usuario": "usuario",
    "id": null,
    "url_perfil": null
  },
  "texto": "Texto da postagem",
  "data_publicacao": null,
  "engajamento": {
    "curtidas": 100,
    "comentarios": 20,
    "compartilhamentos": null,
    "visualizacoes": 5000
  },
  "coletado_em": "2026-10-09T15:00:00Z"
}
```

---

## Exemplo de comentário normalizado

```json
{
  "id": "123456",
  "postagem_url": "https://www.kwai.com/@usuario/video/123",
  "autor": {
    "usuario": "usuario",
    "id": "987654"
  },
  "texto": "Comentário de exemplo",
  "curtidas": 10,
  "data": null,
  "coletado_em": "2026-10-09T00:00:00+00:00"
}
```

Campos que não estejam disponíveis na resposta original podem ser representados como `null`.

---

## Qualidade de código

### Ruff

```bash
poetry run ruff check kwai_collector tests
```

### Mypy

```bash
poetry run mypy kwai_collector
```

### Pytest

```bash
poetry run pytest tests -q
```

Estado validado durante a preparação desta versão:

```text
Ruff: All checks passed
Mypy: Success: no issues found
Pytest: 235 passed
```

---

## Testes

A suíte utiliza mocks, providers falsos e transports controlados para não depender de chamadas reais à rede.

Entre os comportamentos cobertos estão:

- parsing;
- paginação;
- deduplicação;
- retry;
- backoff;
- rate limit;
- checkpoint;
- retomada de coleta;
- configuração;
- CLI;
- providers.

Execução:

```powershell
poetry run pytest tests -q
```

---

## Validação antes da entrega

Execute:

```powershell
poetry run ruff check kwai_collector tests
poetry run mypy kwai_collector
poetry run pytest tests -q
git diff --check
```

---

## Uso responsável

O projeto foi desenvolvido como desafio técnico de coleta de dados públicos.

Seu uso deve respeitar:

- termos e regras da plataforma;
- permissões de acesso;
- privacidade dos usuários;
- limites de requisição;
- legislação aplicável.

Utilize somente dados e integrações que você esteja autorizado a acessar.

---

## Objetivo técnico

A entrega separa comandos, comunicação HTTP, preparação de requisições, persistência e contratos de saída. A [documentação técnica](COLETA_COMENTARIOS.md) descreve o comportamento implementado, os testes e as limitações observadas.

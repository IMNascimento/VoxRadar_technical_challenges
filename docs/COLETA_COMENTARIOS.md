# Coleta de comentários — documentação técnica

**Projeto:** Kwai Collector
**Versão do pacote:** 0.1.0
**Revisão da documentação:** 2.1
**Referência:** 9 de outubro de 2026
**Identificador da entrega:** `A1_Radar`

---

## 1. Visão geral

O Kwai Collector é uma CLI Python para coletar e normalizar dados públicos, com paginação, controle de frequência, recuperação de falhas e testes automatizados.

A implementação separa:

- entrada e validação da CLI;
- casos de uso;
- comunicação HTTP;
- preparação de requisições;
- paginação;
- controle de frequência;
- recuperação de falhas;
- persistência de progresso;
- parsing;
- modelos de domínio;
- configuração.

A coleta retorna **comentários principais** de uma publicação. Respostas e subcomentários estão fora do contrato desta versão; seu suporte exigiria um fluxo e um contrato próprios.

---

## 2. Estado atual

A versão atual possui suporte para:

| Recurso | Estado |
| --- | --- |
| Busca por palavra-chave | Implementado |
| Coleta de postagens de perfil | Implementado |
| Coleta de comentários principais | Implementado |
| Paginação de comentários | Implementado |
| Limite numérico de comentários | Implementado |
| Paginação até condição de término | Implementado |
| Deduplicação | Implementado |
| Retry | Implementado |
| Backoff | Implementado |
| Tratamento de `Retry-After` | Implementado |
| Intervalo configurável entre requisições | Implementado |
| Checkpoint | Implementado |
| Retomada com `--resume` | Implementado |
| Saída JSON normalizada | Implementado |
| Configuração tipada | Implementado |
| Integração mobile por provider | Implementado |
| Assinatura local padrão sem serviço adicional | Implementado e validado em execução real sem configuração |
| Subcomentários/respostas | Não implementado |

---

## 3. Compatibilidade

Os fluxos de busca, perfil e comentários compartilham componentes de coleta e contratos de saída.

O assinador local de comentários é específico de `kwai.lite.video` versão `10.3.20.540101` e de `POST /rest/o/comment/list/v2`. A compatibilidade da arquitetura não significa que esse cálculo possa ser utilizado em qualquer versão ou endpoint.

A lógica de domínio não depende diretamente de uma implementação específica de autenticação, transporte ou origem dos dados.

A camada pública utiliza interfaces e providers para isolar essas responsabilidades.

### 3.1 Ambiente

| Componente | Compatibilidade |
| --- | --- |
| Python | 3.11+ |
| Gerenciamento de dependências | Poetry |
| HTTP | HTTPX |
| HTTP/2 | Suportado pelo cliente mobile |
| Validação | Pydantic |
| Configuração | Pydantic Settings |
| Testes | Pytest |
| Tipagem | Mypy |
| Lint | Ruff |
| CLI | PowerShell e execução via Poetry |

O ambiente principal de desenvolvimento e validação desta entrega utiliza Python 3.11 em Windows com PowerShell.

A maior parte da lógica de aplicação permanece independente do sistema operacional por utilizar Python e bibliotecas multiplataforma.

### 3.2 Compatibilidade de entrada

A aplicação trabalha com diferentes formas de entrada dependendo do comando:

- nome de usuário;
- URL de postagem;
- identificador de postagem;
- palavra-chave.

A resolução de identificadores fica isolada da lógica responsável pela paginação e normalização dos comentários.

### 3.3 Compatibilidade arquitetural

A integração mobile utiliza a abstração `MobileRequestProvider`.

Isso permite substituir a origem autorizada da preparação de requisições sem alterar o restante do fluxo:

```text
CLI
 |
 v
caso de uso
 |
 v
MobileCommentProvider
 |
 v
MobileRequestProvider
 |
 v
cliente HTTP
 |
 v
API
 |
 v
parser
 |
 v
modelo
 |
 v
JSON
```

A compatibilidade descrita nesta documentação refere-se aos contratos e cenários atualmente validados. Mudanças externas na plataforma podem exigir atualização da camada de integração.

---

## 4. Arquitetura

A aplicação utiliza composição entre componentes com responsabilidades específicas.

```text
kwai_collector/
|
|-- clients/
|      comunicação HTTP
|      paginação
|      retry
|      rate limit
|
|-- models/
|      contratos normalizados
|      validação de dados
|
|-- parsers/
|      transformação de respostas externas
|
|-- providers/
|      integração entre clientes e casos de uso
|      checkpoint
|      coleta mobile
|
|-- security/
|      abstrações de preparação de requisição
|      configuração de integração
|
|-- cli.py
|      entry point
|
|-- cli_commands.py
|      comandos de busca e perfil
|
|-- cli_comments.py
|      coleta de uma postagem
|
|-- cli_collect.py
|      coleta agregada
|
|-- cli_builders.py
|      construção de objetos e parâmetros
|
|-- cli_parsers.py
|      definição de argumentos
|
|-- cli_utils.py
|      utilidades da CLI
|
`-- config.py
       configuração tipada
```

---

## 5. Princípios de projeto

A organização atual prioriza:

- responsabilidade única;
- baixo acoplamento;
- dependências explícitas;
- composição em vez de herança;
- validação nas fronteiras;
- funções pequenas;
- nomes orientados à intenção;
- configuração externa;
- tratamento específico de erros;
- testes sem dependência de rede real.

A CLI não concentra regras de protocolo ou paginação.

O cliente HTTP não decide como apresentar o resultado ao usuário.

A CLI é o ponto de composição: seleciona a factory local e injeta sua implementação pelo protocolo `MobileRequestProvider`. A factory genérica mantém a interface para providers alternativos. Essa composição é coberta pelos [testes do provider padrão](../tests/test_default_local_signer.py); os [testes de sig](../tests/test_kwai_lite_103_offline_signer.py) e [sig3](../tests/test_kwai_lite_103_offline_sig3_signer.py) usam vetores de referência. O material empacotado é validado por SHA-256 no carregamento.

Pacote, versão e User-Agent derivam das constantes do signer, e os componentes compartilham a rota do endpoint. Um serviço explicitamente injetado é preservado mesmo quando `bool(service)` é falso; esse comportamento tem teste de regressão. Essas alterações preservam os algoritmos e o material binário.

---

## 6. Fluxo de coleta de comentários

O comando recebe uma URL ou identificador e cria as dependências necessárias para executar a coleta.

Fluxo simplificado:

```text
entrada
  |
  v
validação
  |
  v
resolução do post
  |
  v
seleção do fluxo
  |
  v
provider
  |
  v
cliente HTTP
  |
  v
paginação
  |
  +----> retry / backoff
  |
  +----> rate limit
  |
  +----> checkpoint
  |
  v
deduplicação
  |
  v
parser
  |
  v
Pydantic
  |
  v
JSON
```

Cada responsabilidade pode ser testada isoladamente.

---

## 7. Comentários principais

A versão atual coleta comentários principais.

O fluxo utiliza os registros principais retornados pela fonte de comentários e os normaliza para o modelo público do projeto.

Exemplo:

```json
{
  "id": "1001",
  "postagem_url": "https://www.kwai.com/@usuario/video/1234567890",
  "autor": {
    "usuario": "Usuario",
    "id": "987654"
  },
  "texto": "Comentário de exemplo",
  "curtidas": 12,
  "data": "2026-10-09T12:00:00+00:00",
  "coletado_em": "2026-10-09T15:00:00+00:00"
}
```

Campos indisponíveis na origem podem ser representados como `null` quando permitido pelo modelo.

---

## 8. Subcomentários e respostas

Subcomentários não são coletados nesta versão.

Uma implementação de respostas deverá definir sua relação com o comentário principal e um contrato explícito de saída:

```text
comentário principal
        |
        +---- identificador do comentário raiz
        |
        v
provider de respostas
        |
        v
paginação própria
        |
        v
parser de subcomentários
        |
        v
modelo hierárquico ou coleção relacionada
```

A extensão deverá possuir:

- endpoint/provider próprio;
- paginação independente;
- deduplicação independente;
- rate limit compartilhável;
- testes específicos;
- modelo de relacionamento com o comentário raiz.

O contrato atual de comentários principais deve ser preservado nessa extensão.

---

## 9. Paginação

A paginação é controlada pelo cliente responsável pela coleta.

O comando aceita um limite numérico ou:

```text
todos
```

Exemplo:

```powershell
poetry run kwai-collector comentarios `
    "https://www.kwai.com/@stanleyribeiro/video/5205466849377747864" `
    --max-comments 50 `
    --request-interval 2
```

Para continuar enquanto houver paginação reconhecida:

```powershell
poetry run kwai-collector comentarios `
    "https://www.kwai.com/@stanleyribeiro/video/5205466849377747864" `
    --max-comments todos `
    --request-interval 2
```

A implementação considera condições de encerramento reconhecidas pelo cliente e impede loops de cursor.

---

## 10. Deduplicação

Comentários podem aparecer novamente entre páginas.

Para evitar duplicidade na saída, o fluxo mantém controle dos identificadores já processados.

A primeira ocorrência é preservada.

Esse controle evita exportar novamente um ID recebido em outra página.

---

## 11. Controle de frequência

O intervalo mínimo entre requisições mobile pode ser definido através de:

```text
--request-interval
```

Exemplo:

```powershell
--request-interval 2
```

Também existe configuração por ambiente:

```text
KWAI_MOBILE_PAGE_DELAY
```

O controle de frequência é aplicado pelo cliente responsável pelas chamadas mobile.

O cliente concentra a espera necessária entre chamadas mobile.

---

## 12. Retry e backoff

Falhas temporárias de transporte ou respostas HTTP configuradas como recuperáveis podem ser repetidas.

Configurações:

```text
KWAI_MAX_TENTATIVAS
KWAI_BACKOFF_BASE
```

O backoff cresce entre tentativas até o limite interno.

Quando o servidor fornece um `Retry-After` válido, o cliente respeita o prazo informado.

Erros não classificados como transitórios não entram automaticamente em retry.

Erros de entrada, autenticação ou contrato exigem análise antes de repetir a operação.

---

## 13. Checkpoint

Durante uma coleta paginada, o estado pode ser persistido.

Exemplo de arquivo:

```text
samples/<photo_id>_comentarios.coleta.json
```

O checkpoint pode conter informações necessárias para continuação, como:

- identificação da postagem;
- identificação do autor;
- contexto da listagem;
- próximo cursor;
- comentários já recebidos;
- estado da coleta.

Credenciais de autenticação não fazem parte do contrato de checkpoint.

---

## 14. Retomada

Uma coleta interrompida pode ser retomada:

```powershell
poetry run kwai-collector comentarios `
    "https://www.kwai.com/@stanleyribeiro/video/5205466849377747864" `
    --max-comments todos `
    --request-interval 2 `
    --resume
```

A retomada:

1. carrega o checkpoint;
2. valida sua compatibilidade com a coleta solicitada;
3. recupera o progresso anterior;
4. continua pelo cursor armazenado;
5. preserva resultados existentes;
6. aplica novamente a deduplicação;
7. remove o checkpoint após conclusão e persistência bem-sucedidas.

O limite solicitado inclui os registros anteriormente recuperados.

---

## 15. Recuperação de falhas

Uma falha de paginação pode preservar o progresso recebido.

Quando possível, o fluxo preserva:

- comentários já recebidos;
- cursor pendente;
- checkpoint;
- saída parcial.

O checkpoint permite retomar o progresso preservado sem iniciar a listagem novamente.

---

## 16. Coleta de perfil

Existem dois comportamentos distintos relacionados a perfil.

### `perfil`

```powershell
poetry run kwai-collector perfil "henriqueejuliano" --delay 2
```

Esse comando percorre as páginas disponíveis do perfil até a condição de término reconhecida.

A paginação não possui o antigo limite interno de cinco páginas.

Os posts são deduplicados durante o processo.

### `coletar`

```powershell
poetry run kwai-collector coletar `
    "henriqueejuliano" `
    --max-comments todos `
    --request-interval 2 `
    --delay 2
```

Esse fluxo processa até 10 postagens por execução:

```text
perfil   -> coleta das postagens disponíveis
coletar  -> até 10 postagens + comentários
```

---

## 17. Busca por palavra-chave

Exemplo:

```powershell
poetry run kwai-collector buscar "sertanejo" --delay 2
```

Para incluir comentários:

```powershell
poetry run kwai-collector buscar "sertanejo" `
    --with-comments `
    --max-comments todos `
    --request-interval 2 `
    --delay 2
```

Também é possível definir um limite:

```powershell
poetry run kwai-collector buscar "sertanejo" `
    --with-comments `
    --max-comments 50 `
    --request-interval 2 `
    --delay 2
```

A coleta de comentários reutiliza os mesmos componentes responsáveis por paginação, normalização e controle de frequência.

---

## 18. Configuração mobile

O pacote público trabalha com uma abstração de preparação de requisições.

### 18.1 Provider local padrão

Para limites acima de 20, `todos` e retomadas, a CLI seleciona automaticamente um provider local quando não existe `KWAI_MOBILE_AUTH_ENDPOINT`. O comando de busca com comentários utiliza a mesma composição. A instalação inclui os algoritmos e o material fixo, permitindo execução sem `.env`, token de sessão configurado, Android ou serviço adicional de assinatura.

```text
CLI (composição)
    → criar_local_comment_request_provider
    → CommentListV2RequestProvider
    → KwaiLite103CommentListV2Signer
    → sig + tokensig opcional + sig3
    → factory genérica com delegate
    → perfil mobile e timestamp por chamada
    → LiveCommentClient
    → API do Kwai
```

Na execução, o wrapper aplica o perfil antes de delegar a preparação e a assinatura. O diagrama identifica a composição dos objetos; o timestamp é recalculado para cada tentativa de requisição.

Referências: [composição do provider local](../kwai_collector/security/local_comment_request_provider.py), [assinador composto](../kwai_collector/security/comment_list_v2_signer.py) e [implementação de sig3](../kwai_collector/security/kwai_lite_103_offline_sig3_signer.py).

O cálculo de `sig` ordena os pares completos `chave=valor` como Java, concatena sem separadores e aplica MD5 aos bytes UTF-8 acrescidos do sufixo da versão. Quando existe `client_salt`, tokensig é SHA-256 de `sig + client_salt`. `sig3` combina método, caminho, parâmetros e nonce; reproduz HMAC-SHA256, criptografia por tabelas, CRC32, registro com contexto/contador/tempo e wrapper Base64 URL-safe.

As tabelas estão em `kwai_lite_103_sig3_material.bin`, com 151.616 bytes, incluídas explicitamente no wheel e sdist. A integridade do arquivo é conferida por SHA-256. Esse material fixo não contém a sessão, os cookies ou os tokens do desenvolvedor.

### 18.2 Integração externa opcional

Uma integração autorizada pode ser configurada através de:

```text
KWAI_MOBILE_AUTH_ENDPOINT
KWAI_MOBILE_AUTH_TOKEN
KWAI_MOBILE_AUTH_TIMEOUT
```

Também existem campos configuráveis:

```text
KWAI_MOBILE_QUERY_FIELDS
KWAI_MOBILE_BODY_FIELDS
KWAI_MOBILE_HEADER_FIELDS
```

O provider prepara a requisição; a camada de coleta consome a interface resultante.

Essas variáveis são opcionais para o fluxo padrão. Se o endpoint externo estiver explicitamente configurado, ele substitui o provider local. A factory continua aceitando um `MobileRequestProvider` injetado, preservando a arquitetura refatorada e os testes de providers alternativos.

### 18.3 Validação sem configuração

Em 9 de outubro de 2026, o wheel construído a partir desta implementação foi extraído em um diretório isolado, com outra pasta de trabalho. O teste removeu variáveis `KWAI_*`, confirmou ausência de `.env`, endpoint, token, cookie e templates configurados, e verificou que o módulo importado pertencia ao pacote isolado.

| Comando | Saída | IDs únicos | Código de saída |
| --- | ---: | ---: | ---: |
| `comentarios <URL> --max-comments 50 --request-interval 2` | 50 comentários | 50 | 0 |
| `comentarios <URL> --max-comments todos --request-interval 2` | 88 comentários | 88 | 0 |

Ambos usaram a postagem pública `5257539724123961717` de `henriqueejuliano`. Os checkpoints foram removidos após a conclusão. A consulta inicial independente também confirmou duas páginas de 20 comentários com HTTP 200 e `result=1`, sem credenciais salvas.

O [relatório de validação](validations/clone_sem_configuracao_2026-10-09.json) registra os resultados, a ausência de configuração e os hashes do wheel e do material fixo. Esse teste demonstra o comportamento real na data registrada; a disponibilidade e as respostas futuras continuam dependentes da plataforma.

### 18.4 Validação real dos comandos de perfil e busca

Os três comandos seguintes também foram executados com o wheel isolado em outra pasta de trabalho, sem `.env`, variáveis `KWAI_*`, token ou cookie salvo. O intervalo configurado foi de dois segundos. A consulta de perfil e a busca utilizaram os endpoints públicos; a coleta de comentários utilizou o provider local padrão.

```powershell
poetry run kwai-collector perfil "henriqueejuliano" --delay 2

poetry run kwai-collector coletar "henriqueejuliano" --max-comments todos --request-interval 2 --delay 2

poetry run kwai-collector buscar "sertanejo" --with-comments --max-comments 50 --request-interval 2 --delay 2
```

Cada execução recebeu uma pasta de saída própria para permitir conferência independente dos arquivos.

| Fluxo | Posts processados | Comentários principais únicos | Código de saída | Erros de comentários |
| --- | ---: | ---: | ---: | ---: |
| Listagem de perfil | 191 | Não aplicável | 0 | Não aplicável |
| Perfil com `todos` | 10 | 1.116 | 0 | 0 |
| Busca com limite 50 por post | 50 | 1.475 | 0 | 0 |

A conferência não usou somente o código de saída. Ela confirmou que as quantidades por postagem correspondem ao tamanho das listas, que as somas correspondem aos totais declarados, que os IDs de comentários são únicos por post e também nos dois agregados, e que não existem registros `erro` ou checkpoints pendentes nas coletas de comentários.

Na coleta dos dez posts, os detalhes também foram obtidos sem `erro_detalhes`. As quantidades foram `[11, 5, 18, 35, 30, 13, 87, 52, 350, 515]`, cuja soma é 1.116. Esse é o resultado desta consulta, distinto dos 1.119 registrados em uma execução anterior.

A busca encontrou cinquenta posts e processou todos eles. Nenhuma lista final excedeu cinquenta comentários. Três posts retornaram zero comentários disponíveis; os demais produziram um total agregado de 1.475. O arquivo agregado declarou `complete=true`, e os arquivos individuais coincidiram com as listas do agregado.

A listagem do perfil terminou com um aviso de **cursor repetido**. Portanto, 191 é a quantidade de posts únicos recebidos até esse critério de encerramento, e não uma comprovação de esgotamento de todo o histórico.

O post `5257539724123961717` retornou 88 comentários principais únicos na validação individual descrita na seção anterior e 87 no agregado posterior. Os arquivos demonstram a diferença de retorno; não permitem determinar sua causa. O limite `todos` segue a paginação disponível e não fixa uma quantidade permanente para uma postagem.

O [relatório dos três fluxos](validations/fluxos_sem_configuracao_2026-10-09.json) registra o hash do mesmo wheel validado, os argumentos, as quantidades, os critérios conferidos e a ausência de configuração de sessão. Nenhum resultado dessas tabelas foi produzido por `MockTransport`.

### 18.5 Resultado final da busca com todos os comentários principais

A avaliação da busca utilizou o mesmo wheel isolado, sem `.env`, configuração `KWAI_*`, cookies, tokens salvos ou serviço externo de assinatura. O comando de busca utilizado foi:

```powershell
poetry run kwai-collector buscar "sertanejo" --with-comments --max-comments todos --request-interval 2 --delay 2
```

A busca retornou cinquenta posts. O resultado final consolidado utiliza essa amostra. Uma nova busca pode retornar outros posts; por isso, o total não deve ser comparado diretamente aos 1.475 comentários do teste anterior como se as duas amostras fossem iguais.

| Verificação do resultado final | Resultado |
| --- | ---: |
| Posts processados | 50 |
| Comentários principais | 8.893 |
| IDs únicos de comentários no agregado | 8.893 |
| Posts com mais de 50 comentários | 20 |
| Maior quantidade em um post | 1.884 |
| Posts sem comentários retornados | 4 |
| Erros pendentes de comentários | 0 |
| Checkpoints pendentes na pasta de coleta | 0 |

A conferência do agregado final confirmou a seleção de cinquenta IDs de posts, limite de comentários `null`, quantidades correspondentes às listas, soma total, IDs únicos, igualdade entre arquivos individuais e agregado, `complete=true` e ausência de checkpoints pendentes. Foram coletados somente comentários principais; o total representa os registros disponíveis na amostra, sem comprovar igualdade com os contadores públicos ou incluir subcomentários.

O [relatório da busca com `todos`](validations/busca_sertanejo_todos_sem_configuracao_2026-10-09.json) registra os parâmetros da avaliação e as verificações do resultado final.

---

## 19. Segurança de configuração

Credenciais reais não devem ser versionadas.

O arquivo:

```text
.env
```

deve permanecer fora do Git.

O repositório público deve utilizar apenas exemplos sem valores reais.

Dados coletados em `samples/`, JSONs de comentários, checkpoints e backups não entram no commit de entrega. Os artefatos de validação versionáveis limitam-se a relatórios estatísticos sem textos de comentários ou credenciais e fixtures de teste revisadas.

Também não devem ser publicados:

- tokens ativos;
- cookies de sessão;
- URLs autenticadas;
- dumps contendo credenciais;
- backups de configuração;
- artefatos técnicos privados.

---

## 20. Contrato dos comentários

Modelo conceitual:

| Campo | Tipo |
| --- | --- |
| `id` | `str \| None` |
| `postagem_url` | `str` |
| `autor.usuario` | `str \| None` |
| `autor.id` | `str \| None` |
| `texto` | `str` |
| `curtidas` | `int \| None` |
| `data` | ISO 8601 ou `null` |
| `coletado_em` | ISO 8601 |

Campos obrigatórios para a saída normalizada:

```text
postagem_url
texto
coletado_em
```

---

## 21. Persistência

Os resultados são gravados em JSON.

Exemplos:

```text
samples/<photo_id>_comentarios.json
samples/<usuario>_posts.json
samples/<usuario>_comentarios.json
samples/busca_<termo>.json
samples/busca_<termo>_comentarios.json
```

O conteúdo de saída é separado da configuração operacional utilizada para realizar as requisições.

---

## 22. Testabilidade

Os testes automatizados não dependem da disponibilidade da API real.

São utilizados:

- mocks;
- providers falsos;
- transports controlados;
- fixtures;
- dependências injetadas.

Os testes verificam de forma determinística:

- múltiplas páginas;
- fim de paginação;
- cursor repetido;
- comentários duplicados;
- HTTP temporariamente indisponível;
- retry;
- backoff;
- `Retry-After`;
- checkpoint;
- retomada;
- configuração;
- CLI.

---

## 23. Estado de qualidade

Na validação da versão atual:

```text
Ruff
All checks passed!

Mypy
Success: no issues found in 59 source files

Pytest
235 passed
```

Comandos utilizados:

```powershell
poetry run ruff check kwai_collector tests
poetry run mypy kwai_collector
poetry run pytest tests -q
```

Os números acima representam o estado validado desta versão e devem ser atualizados quando a suíte mudar.

---

## 24. Tratamento de erros

O fluxo diferencia erros de acordo com sua natureza.

Exemplos:

```text
entrada inválida
        -> rejeição pela CLI

falha temporária de rede
        -> retry quando aplicável

erro HTTP transitório
        -> retry/backoff quando configurado

erro permanente
        -> interrupção

falha depois de páginas válidas
        -> preservação de progresso quando possível
```

Cada categoria determina se a operação pode repetir a chamada, preservar progresso ou encerrar.

---

## 25. Observabilidade

Os logs são utilizados para informar:

- início da operação;
- progresso de páginas;
- quantidade acumulada;
- tentativas;
- espera;
- falhas;
- conclusão;
- caminhos dos arquivos gerados.

Dados sensíveis não devem fazer parte de logs públicos.

---

## 26. Escalabilidade e evolução

As extensões abaixo dependem de implementação e testes próprios:

### Subcomentários

Adicionar respostas utilizando um fluxo dedicado e relacionamento com comentário raiz.

### Persistência de grandes volumes

Substituir progressivamente estruturas inteiramente em memória por persistência incremental quando o volume justificar.

### Rate limit compartilhado

Caso o projeto adote concorrência ou múltiplos workers, o limitador poderá evoluir para coordenação compartilhada.

### Resultado de coleta enriquecido

Um contrato futuro pode registrar explicitamente:

- motivo do término;
- último cursor;
- quantidade bruta;
- quantidade única;
- completude;
- duração;
- estatísticas de retry.

### Providers adicionais

Novos providers podem ser incorporados sem alterar os casos de uso principais.

---

## 27. Decisão sobre subcomentários

A versão atual não retorna respostas de comentários. Uma extensão para subcomentários deve possuir contrato e testes próprios, sem modificar a semântica de:

```text
--max-comments
```

Hoje esse valor representa comentários principais.

Uma versão futura poderá oferecer uma opção explícita, por exemplo:

```text
incluir respostas
```

mantendo consumidores atuais compatíveis com o formato já entregue.

---

## 28. Limitações conhecidas

As limitações atuais incluem:

- subcomentários ainda não são coletados;
- o provider local foi validado sem sessão configurada para os comentários públicos testados; dados protegidos ou mudanças na plataforma podem exigir outra integração;
- mudanças da plataforma podem exigir adaptação da integração;
- rate limit atual é local ao processo/cliente;
- coletas agregadas mantêm limite operacional de posts;
- a completude depende dos critérios de paginação disponíveis na resposta;
- grandes coleções ainda são acumuladas em memória durante determinados fluxos.

---

## 29. Compatibilidade futura

Alterações nos seguintes detalhes da integração devem permanecer concentradas em providers e clients:

- autenticação;
- transporte;
- headers;
- campos de protocolo;
- origem da requisição;

Mudanças nos contratos de saída exigem revisão dos modelos, parsers e consumidores. Recursos novos, como subcomentários, devem ter integração e contrato explícitos.

---

## 30. Comandos principais

### Ajuda

```powershell
poetry run kwai-collector --help
```

### Perfil

```powershell
poetry run kwai-collector perfil "henriqueejuliano" --delay 2
```

### Coleta agregada

```powershell
poetry run kwai-collector coletar `
    "henriqueejuliano" `
    --max-comments todos `
    --request-interval 2 `
    --delay 2
```

### Comentários

```powershell
poetry run kwai-collector comentarios `
    "https://www.kwai.com/@stanleyribeiro/video/5205466849377747864" `
    --max-comments todos `
    --request-interval 2
```

### Comentários limitados

```powershell
poetry run kwai-collector comentarios `
    "https://www.kwai.com/@stanleyribeiro/video/5205466849377747864" `
    --max-comments 50 `
    --request-interval 2
```

### Retomada

```powershell
poetry run kwai-collector comentarios `
    "https://www.kwai.com/@stanleyribeiro/video/5205466849377747864" `
    --max-comments todos `
    --request-interval 2 `
    --resume
```

### Busca

```powershell
poetry run kwai-collector buscar "sertanejo" --delay 2
```

### Busca com comentários

```powershell
poetry run kwai-collector buscar "sertanejo" `
    --with-comments `
    --max-comments todos `
    --request-interval 2 `
    --delay 2
```

---

## 31. Validação para entrega

Antes de uma versão ou commit de entrega:

```powershell
poetry run ruff check kwai_collector tests
poetry run mypy kwai_collector
poetry run pytest tests -q
git diff --check
```

Também devem ser revisados:

```text
git status
.gitignore
.env.example
pyproject.toml
poetry.lock
README.md
docs/
```

O commit de entrega deve conter código, testes e documentação, sem exportações de comentários, checkpoints, backups ou credenciais. Entre os artefatos de validação, incluir apenas relatórios estatísticos e fixtures de teste revisadas.

---

## 32. Conclusão

A versão atual oferece busca, perfil e coleta de comentários principais, com paginação, controle de frequência, deduplicação e recuperação de progresso. A assinatura local padrão foi validada nas consultas públicas registradas na seção 18.

Os resultados consolidados e os critérios de conferência estão registrados nos relatórios de validação. Respostas e subcomentários permanecem fora do escopo, e a conclusão da paginação não comprova esgotamento do histórico nem igualdade com contadores públicos.

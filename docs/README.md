# Documentação do Kwai Collector

Referência de uso, integração Python e manutenção do projeto `kwai-scraper`.
O coletor lê dados públicos por HTTP e produz modelos tipados ou listas JSON.
Não é um SDK oficial do Kwai, nem uma API pública com garantia de compatibilidade.

## Comece aqui

| Sua situação | Abra |
|---|---|
| Nunca executei o projeto | [Primeiros passos: instalar e fazer a primeira coleta](./guides/getting-started.md). |
| Já instalei e quero copiar um comando | [CLI: escolha o que coletar](./guides/cli.md#comandos-por-objetivo). |
| Quero entender onde o JSON é salvo | [Destino e versões](./guides/cli.md#destino-e-versões). |
| O comando falhou ou gerou um parcial | [Falhas e parciais](./guides/cli.md#falhas-e-parciais). |
| Quero chamar pelo meu programa Python | [Referência Python](./reference/api-reference.md). |

Com Python e Poetry instalados, execute na pasta que contém `pyproject.toml`:

```bash
poetry install
poetry run kwai-collector profile --user parkourcity --limit 3
```

Substitua o perfil pelo alvo desejado. A coleta faz rede. Sem `--out`, o arquivo
fica em `exports/parkourcity/<execução>/posts.json`; o terminal informa a pasta.
Para comentários de cada postagem, use `--with-comments`; para comentários com
respostas, `--with-comments-replies`. A [CLI](./guides/cli.md) explica os limites e
como gerar ambas as versões, sem precisar entender o protocolo interno.

## Referência técnica

Esta documentação descreve a implementação atual, não propõe uma arquitetura nova.
Os guias de pesquisa foram adaptados dos documentos de experimentos: caminhos,
nomes e procedimentos foram atualizados; propostas abandonadas não viraram
funcionalidades. A [proveniência](./maintenance/research.md) registra essa adaptação.

## Navegação

| Documento | Conteúdo |
|---|---|
| [Primeiros passos](./guides/getting-started.md) | Requisitos, instalação, configuração, CLI e limites de operação. |
| [CLI e exportação](./guides/cli.md) | Comandos em inglês, coleta combinada, pastas, duas versões e parciais. |
| [Referência Python](./reference/api-reference.md) | Serviços, casos de uso, adapters, portas, recursos e exceções. |
| [Arquitetura](./internals/architecture.md) | Organização do código, dependências e composição. |
| [Regras de negócio](./business-rules/README.md) | Políticas numeradas de coleta, contrato e falhas, com implementação e testes. |
| [Fluxos e pipelines](./flows/README.md) | Ciclo de vida, busca, perfil, comentários e paginação em diagramas. |
| [Casos de uso](./use-cases/README.md) | UC-001 a UC-003: entradas, pré-condições, passos, alternativas e saídas. |
| [ADRs e trade-offs](./adr/README.md) | Escolhas adotadas, alternativas, ganhos, custos e condições de revisão. |
| [Assinatura e sal](./internals/signature.md) | O que é `sig`, fórmula, canonicalização, identidade do app e testes. |
| [Protocolo móvel](./internals/mobile-api.md) | Rotas, parâmetros, contextos, gateways e retry. |
| [Schemas e mapeamento](./reference/schemas.md) | Campos de saída, tipos, exemplos e limites da validação. |
| [Manutenção](./maintenance/maintenance.md) | Diagnóstico, smoke, atualização de versão, evidências e checklist. |
| [Pesquisa e decisões históricas](./maintenance/research.md) | Origem da solução, alternativas descartadas e o que permanece desconhecido. |

## Organização por responsabilidade

```text
docs/
├── README.md                 # Índice principal
├── _sidebar.md               # Mapa de navegação
├── guides/                   # Uso e operação
│   ├── getting-started.md
│   └── cli.md
├── reference/                # Contratos públicos
│   ├── api-reference.md
│   └── schemas.md
├── internals/                # Implementação e protocolo
│   ├── architecture.md
│   ├── mobile-api.md
│   └── signature.md
├── maintenance/              # Diagnóstico e evidências
│   ├── maintenance.md
│   └── research.md
├── business-rules/           # Regras RN-001 a RN-015
│   ├── README.md
│   ├── collection.md
│   ├── data-contract.md
│   └── failure-policy.md
├── flows/                    # Um fluxo por página
│   ├── README.md
│   ├── runtime.md
│   ├── search.md
│   ├── profile.md
│   ├── comments.md
│   └── pagination.md
├── use-cases/                # Três operações expostas ao chamador
│   ├── README.md
│   ├── uc-001-search-posts.md
│   ├── uc-002-collect-user-posts.md
│   └── uc-003-collect-comments.md
└── adr/                      # Cinco decisões retrospectivas
    ├── README.md
    ├── 0001-mobile-profile-and-comments.md
    ├── 0002-local-signature.md
    ├── 0003-page-ports-and-pagination.md
    ├── 0004-partial-results-and-declared-counts.md
    └── 0005-entities-as-output-contract.md
```

**Regra** define condição e consequência. **Fluxo** mostra como componentes
executam essa política. **Caso de uso** descreve o comportamento para o chamador.
**ADR** registra a escolha e o custo assumido. Essas páginas se referenciam;
não representam quatro definições independentes do mesmo comportamento.

Todos os documentos estão a até dois links do índice. O
[mapa lateral](./_sidebar.md) também reúne a navegação. A documentação continua
em Markdown, sem build ou dependência nova para consultar os arquivos.

## Por onde começar

| Necessidade | Leitura recomendada |
|---|---|
| Executar uma coleta | Primeiros passos → CLI e exportação. |
| Integrar em outro programa Python | Referência Python → Casos de uso → Fluxos. |
| Entender uma rejeição da API | Manutenção → Protocolo móvel → Assinatura. |
| Atualizar o contexto do app | Assinatura → Manutenção → Pesquisa. |
| Alterar uma funcionalidade | Regras → Caso de uso → Fluxo → testes listados na Manutenção. |
| Entender por que uma alternativa não foi adotada | ADRs → Pesquisa. |

## Limites que atravessam todos os guias

- Busca usa a API web; perfil, comentários e respostas usam a API móvel.
- O fluxo de coleta não implementa login nem precisa de cookies fornecidos,
  navegador, Android, Frida, Java, `.so` ou serviço de assinatura de terceiros.
- `sig` é calculado localmente. `__NS_sig3` não é implementado nem enviado.
- Endpoints externos podem mudar sem aviso. Testes offline não provam disponibilidade.
- Fim de cursor não prova que todo o conteúdo da plataforma foi entregue.
- Dados de cada unidade ficam em memória. A CLI nova grava por unidade; não há checkpoint, retomada ou banco.
- Os exemplos que fazem coleta exigem rede; os exemplos de assinatura e modelos
  podem ser executados offline.

## Convenções

Os imports reais começam com `src`, apesar de o pacote instalado se chamar
`kwai-collector`. Nomes Python como `Post` e `Comment` convivem com campos JSON
em português; não renomeie campos da saída ao copiar um exemplo.

O código e os testes são a referência do comportamento. Procedimentos indicados
como recomendações não são automações já instaladas. As capturas históricas são
observações de versões e amostras específicas, não especificações do servidor.

Instalação, comandos e configuração estão no [README do projeto](../README.md).

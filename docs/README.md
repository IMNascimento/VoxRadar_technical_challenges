# Documentação do Kwai Collector

Referência de uso, integração Python e manutenção do projeto `kwai-collector`.
O coletor lê dados públicos do Kwai por HTTP e produz listas JSON nos formatos
`Postagem` e `Comentario` do desafio VoxRadar (nível 1).
Não é um SDK oficial do Kwai, nem uma API pública com garantia de compatibilidade.

## Comece aqui

| Sua situação | Abra |
|---|---|
| Nunca executei o projeto | [Primeiros passos: instalar e fazer a primeira coleta](./guides/getting-started.md). |
| Já instalei e quero copiar um comando | [CLI: comandos por objetivo](./guides/cli.md#comandos-por-objetivo). |
| Quero entender onde o JSON vai parar | [Destino da saída](./guides/cli.md#destino-da-saída). |
| O comando falhou | [Falhas e códigos de saída](./guides/cli.md#falhas-e-códigos-de-saída). |
| Quero chamar pelo meu programa Python | [Referência Python](./reference/api-reference.md). |

Com Python e Poetry instalados, execute na pasta que contém `pyproject.toml`:

```bash
poetry install
poetry run kwai-collector profile --user parkourcity --limit 3 --out out/usuario.json
```

Substitua o perfil pelo alvo desejado. A coleta faz rede. Sem `--out`, o JSON
é impresso no terminal. Para comentários de uma postagem, use o comando
`comments`; para incluir as respostas, acrescente `--with-replies`. A
[CLI](./guides/cli.md) explica os limites de cada comando sem exigir que você
entenda o protocolo interno.

## Referência técnica

Esta documentação descreve a implementação atual. O código e os testes são a
fonte de verdade: quando um texto daqui divergir do código, vale o código, e a
documentação deve ser corrigida.

## Navegação

| Documento | Conteúdo |
|---|---|
| [Primeiros passos](./guides/getting-started.md) | Requisitos, instalação, primeira coleta, configuração e problemas comuns. |
| [CLI](./guides/cli.md) | Comandos, opções, destino da saída, limites e códigos de saída. |
| [Referência Python](./reference/api-reference.md) | Funções públicas de cada módulo, exceções e exemplos de uso. |
| [Arquitetura](./internals/architecture.md) | Organização em módulos, dependências e ciclo de uma execução. |
| [Regras de negócio](./business-rules/README.md) | Políticas numeradas de coleta, contrato e falhas, com implementação e testes. |
| [Fluxos e pipelines](./flows/README.md) | Ciclo de vida, busca, perfil, comentários e paginação em diagramas. |
| [Casos de uso](./use-cases/README.md) | UC-001 a UC-003: entradas, pré-condições, passos, alternativas e saídas. |
| [ADRs e trade-offs](./adr/README.md) | Escolhas adotadas, alternativas, ganhos, custos e condições de revisão. |
| [Assinatura e sal](./internals/signature.md) | O que é `sig`, fórmula, canonicalização, identidade do app e testes. |
| [Protocolo móvel](./internals/mobile-api.md) | Rotas, parâmetros, contextos, hosts e retry. |
| [Schemas e mapeamento](./reference/schemas.md) | Campos de saída, tipos, exemplos e limites da validação. |
| [Manutenção](./maintenance/maintenance.md) | Diagnóstico, verificação offline, smoke, atualização de versão e checklist. |
| [Pesquisa e evidências](./maintenance/research.md) | Origem da solução, alternativas descartadas e o que permanece desconhecido. |

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
├── business-rules/           # Regras RN-001 a RN-016
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
├── use-cases/                # As três operações do desafio
│   ├── README.md
│   ├── uc-001-search-posts.md
│   ├── uc-002-collect-user-posts.md
│   └── uc-003-collect-comments.md
└── adr/                      # Seis decisões registradas
    ├── README.md
    ├── 0001-mobile-profile-and-comments.md
    ├── 0002-local-signature.md
    ├── 0003-flat-modules.md
    ├── 0004-all-or-nothing-output.md
    ├── 0005-pydantic-output-models.md
    └── 0006-single-output-file.md
```

**Regra** define condição e consequência. **Fluxo** mostra como os módulos
executam essa política. **Caso de uso** descreve o comportamento para quem
chama. **ADR** registra a escolha e o custo assumido. Essas páginas se
referenciam; não são quatro definições independentes do mesmo comportamento.

Todos os documentos estão a até dois links deste índice. O
[mapa lateral](./_sidebar.md) também reúne a navegação. A documentação é
Markdown puro, sem build nem dependência nova para consultar os arquivos.

## Por onde começar

| Necessidade | Leitura recomendada |
|---|---|
| Executar uma coleta | Primeiros passos → CLI. |
| Integrar em outro programa Python | Referência Python → Casos de uso → Fluxos. |
| Entender uma rejeição da API | Manutenção → Protocolo móvel → Assinatura. |
| Atualizar a versão do app de referência | Assinatura → Manutenção → Pesquisa. |
| Alterar uma funcionalidade | Regras → Caso de uso → Fluxo → testes listados na Manutenção. |
| Entender por que uma alternativa não foi adotada | ADRs → Pesquisa. |

## Limites que atravessam todos os guias

- A busca usa a API web; perfil, comentários e respostas usam a API móvel.
- A coleta não faz login nem precisa de cookies, navegador, Android, Frida,
  Java, `.so` ou serviço de assinatura de terceiros.
- `sig` é calculado localmente. `__NS_sig3` não é implementado nem enviado.
- Endpoints externos podem mudar sem aviso. Testes offline não provam disponibilidade.
- Fim de cursor não prova que todo o conteúdo da plataforma foi entregue.
- Os dados ficam em memória até o fim do comando. Se a coleta falhar no meio,
  nada é salvo: não há resultado parcial, checkpoint ou retomada.
- Os exemplos que fazem coleta exigem rede; os exemplos de assinatura e de
  modelos podem ser executados offline.

## Convenções

O pacote Python se chama `kwai_collector` e o comando instalado,
`kwai-collector`. Nomes Python como `Post` e `Comment` convivem com campos JSON
em português; não renomeie campos da saída ao copiar um exemplo.

Procedimentos indicados como recomendações não são automações instaladas no
projeto. Capturas citadas são observações de versões e amostras específicas,
não especificações do servidor.

Instalação, comandos e configuração resumidos estão no [README do projeto](../README.md).

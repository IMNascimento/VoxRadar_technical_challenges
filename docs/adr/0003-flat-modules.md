[⬅️ ADRs](./README.md) · [🏠 Índice](../README.md)

# ADR-0003 — Módulos por responsabilidade, sem camadas

| | |
|---|---|
| **Status** | ✅ Aceita — adotada no código atual. |
| **Data** | 2026-10-09 — registro retrospectivo. |
| **Escopo** | Organização de todo o pacote `kwai_collector`. |

## Contexto

O nível 1 do desafio pede cliente, parsing, modelos e CLI em módulos distintos,
com type hints e testes. A avaliação do desafio conta complexidade sem
propósito contra a solução e simplicidade adequada ao nível a favor. As três
operações são leituras sequenciais, sem estado entre execuções, sem banco e sem
regra de negócio além de limite, deduplicação e paginação.

## Alternativas

**A — Camadas com portas e adaptadores (DDD/hexagonal):** isola o domínio do
HTTP e permite testar a coleta com fakes, mas multiplica arquivos, interfaces e
objetos de transferência para um problema pequeno.

**B — Um script único:** o menor código possível, mas mistura HTTP, conversão,
contrato e CLI, e não atende à separação pedida no nível 1.

**C — Módulos por responsabilidade, com funções:** `client`, `parser`,
`models`, `scraper`, `cli` e `config`, sem classes de serviço nem injeção de
dependência.

## Decisão

Adotar **C**. Cada módulo expõe funções; a configuração é uma instância única
criada na importação; o rate limit é um estado global em `client.py`. O
scraper chama o client diretamente e conhece as rotas e os corpos do Kwai.

## Trade-offs

- **Ganhamos:** cerca de 700 linhas em 7 arquivos, leitura linear de ponta a
  ponta e a separação client / parser / models / cli que o desafio pede.
- **Abrimos mão de:** testar a coleta sem simular HTTP. Os testes de fluxo usam
  `respx` no nível do transporte, não fakes de uma interface.
- **Custo:** `scraper.py` conhece rotas, corpos e tamanhos de página; uma mudança
  na API do Kwai mexe em `scraper.py` e às vezes em `client.py` e `parser.py`.
- **Risco:** o estado global (`settings` e `_last_request`) impede usar o
  coletor em paralelo dentro do mesmo processo com garantias de ritmo.
- **Revisitar quando:** surgir uma segunda fonte de dados para a mesma
  operação, persistência, execução concorrente ou regra de negócio que mude o
  estado dos itens.

## Consequências e verificação

O grafo de imports não tem ciclos: `cli` importa `scraper` e `client`;
`scraper` importa `client`, `parser` e `models`; `parser` importa `models`;
`client` importa `config`. `parser.py` e `models.py` são testados sem rede.

[Arquitetura](../internals/architecture.md) · [Referência Python](../reference/api-reference.md).

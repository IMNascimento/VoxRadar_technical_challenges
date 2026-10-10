[⬅️ Voltar ao índice principal](../README.md)

# 🧭 Decisões e trade-offs

Estas ADRs são **registros retrospectivos** da implementação e das restrições
já confirmadas, não aprovação de uma arquitetura nova. A data de cada página
é a data do registro documental; não reconstrói a data original da escolha.

| ADR | Decisão | Principal custo assumido |
|---|---|---|
| [0001 — Superfícies de coleta](./0001-mobile-profile-and-comments.md) | Busca web; perfil/comentários móveis; sem fallback SSR/browser. | Dependência de protocolo móvel externo. |
| [0002 — Assinatura local](./0002-local-signature.md) | `sig` em Python, sem signer nativo em runtime. | Compatibilidade ligada à identidade validada. |
| [0003 — Portas de página](./0003-page-ports-and-pagination.md) | Adapter entrega página; aplicação controla paginação. | Mais contratos e manutenção de semânticas diferentes. |
| [0004 — Parcial e contagens](./0004-partial-results-and-declared-counts.md) | Preservar parcial; declaração não significa completude. | Consumidor deve distinguir parcial/warning de resultado completo. |
| [0005 — Entidades como saída](./0005-entities-as-output-contract.md) | Entidades do domínio são o schema JSON; sem DTOs de saída. | Mudança no contrato JSON altera o domínio. |

Status “aceita” significa **adotada no código examinado**, não avaliada
independentemente nesta tarefa. Alternativas descrevem caminhos encontrados no
histórico/documentação ou contrastes com o comportamento anterior; não são
promessas de alternativas prontas e disponíveis hoje.

Ao mudar uma decisão no futuro, registrar outra ADR e marcar a anterior como
substituída com referência à nova. Não apagar o histórico para fazê-lo parecer
que sempre esteve alinhado ao estado atual.

Relacionados: [Arquitetura](../internals/architecture.md), [Pesquisa](../maintenance/research.md),
[Regras](../business-rules/README.md) e [Manutenção](../maintenance/maintenance.md).

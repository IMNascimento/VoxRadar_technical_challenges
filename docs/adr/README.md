[⬅️ Voltar ao índice principal](../README.md)

# 🧭 Decisões e trade-offs

Estas ADRs são **registros retrospectivos** das escolhas presentes no código,
não propostas de arquitetura nova. A data de cada página é a data do registro
documental.

| ADR | Decisão | Principal custo assumido |
|---|---|---|
| [0001 — Superfícies de coleta](./0001-mobile-profile-and-comments.md) | Busca na web; perfil e comentários na API móvel; sem fallback para navegador. | Dependência de um protocolo móvel externo e não oficial. |
| [0002 — Assinatura local](./0002-local-signature.md) | `sig` calculado em Python, sem assinador nativo. | Compatibilidade presa à versão do app validada. |
| [0003 — Módulos planos](./0003-flat-modules.md) | Módulos por responsabilidade, sem camadas nem portas. | Testes dependem de simular HTTP; mudança de API mexe em mais de um módulo. |
| [0004 — Saída tudo ou nada](./0004-all-or-nothing-output.md) | Sem resultado parcial: falha no meio descarta tudo. | Coletas longas perdem o progresso numa falha tardia. |
| [0005 — Modelos Pydantic](./0005-pydantic-output-models.md) | Modelos Pydantic validam o contrato de saída. | Dependência a mais e `ValidationError` não tratada na CLI. |
| [0006 — Arquivo único ou stdout](./0006-single-output-file.md) | `--out` é um arquivo; sem ele, stdout. | Sobrescreve execuções anteriores; sem histórico automático. |

Status “aceita” significa **adotada no código atual**. As alternativas
descrevem caminhos considerados, não opções prontas disponíveis hoje.

Ao mudar uma decisão, registre outra ADR e marque a anterior como substituída
(♻️), com link para a nova. Não apague o histórico.

Relacionados: [Arquitetura](../internals/architecture.md),
[Pesquisa](../maintenance/research.md), [Regras](../business-rules/README.md) e
[Manutenção](../maintenance/maintenance.md).

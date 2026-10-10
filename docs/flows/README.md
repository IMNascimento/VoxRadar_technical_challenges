[⬅️ Voltar ao índice principal](../README.md)

# 🔀 Fluxos e pipelines

Os diagramas representam a implementação síncrona atual: não há workers, banco,
fila nem assinador externo escondido no fluxo.

| Fluxo | Entrada → saída | Relacionados |
|---|---|---|
| [Ciclo de vida](./runtime.md) | CLI → coleta → serialização → código de saída. | Todas as operações. |
| [Busca](./search.md) | Palavras-chave → lista de `Post`. | UC-001. |
| [Perfil](./profile.md) | Usuário → id → páginas → lista de `Post`. | UC-002. |
| [Comentários](./comments.md) | URL → comentários principais → respostas opcionais. | UC-003. |
| [Paginação](./pagination.md) | Cursor → páginas → fim. | Perfil, comentários e respostas. |

Fontes: [`scraper.py`](../../kwai_collector/scraper.py) (limites, paginação e
dedupe), [`client.py`](../../kwai_collector/client.py) (HTTP) e
[`parser.py`](../../kwai_collector/parser.py) (conversão). Veja
[Arquitetura](../internals/architecture.md), [Regras](../business-rules/README.md)
e [Casos de uso](../use-cases/README.md).

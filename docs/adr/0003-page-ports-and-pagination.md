[⬅️ ADRs](./README.md) · [🏠 Índice](../README.md)

# ADR-0003 — Separar portas de página da política de paginação

| | |
|---|---|
| **Status** | ✅ Aceita — adotada no código examinado. |
| **Data** | 2026-10-08 — registro retrospectivo, não data original comprovada. |
| **Escopo** | Busca, perfil, raízes e sublistas. |

## Contexto

Perfil e comentários precisam de cursor, fim de página, dedupe e limites, mas
não têm a mesma semântica de contagem. Casos de uso devem ser exercitados sem
HTTP, enquanto o adapter conhece payload, hosts e assinatura.

## Alternativas

**A — Loops próprios em cada caso de uso:** mantém a lógica local, mas replica
controle de cursor/fim e pode fazer tratamentos de loop divergirem por acidente.

**B — Adapter coletar toda a lista:** concentra operação HTTP, mas mistura
paginação com limite, parcial e dedupe, reduzindo o controle do consumidor.

**C — Porta devolve página e aplicação usa gerador comum:** compartilha a
mecânica de continuação, preservando as políticas de cada operação.

## Decisão

Adapters retornam `ProfilePage`, `CommentPage` ou `SubCommentPage` pelas portas
da aplicação (`IProfileApiPort`, `ICommentApiPort`, classes abstratas).
`iter_pages`, na aplicação, coordena a busca sob demanda e mantém os cursores
vistos. `get_continuation_cursor`, serviço puro de domínio, decide fim e
repetição sem executar callbacks de I/O nem alterar a coleção recebida.
Casos de uso acumulam, deduplicam, aplicam limite e tratam interrupções.

Uma página é entregue antes da checagem de sua continuação. Ao atingir limite,
o consumidor pode parar sem fazer chamada extra. A resposta mapeada vazia é
condição de fim. Não adicionar checkpoint, streaming público ou plugin registry
como consequência desse gerador interno.

## Trade-offs

- **Ganhamos:** teste de caso de uso com fake, isolamento de HTTP e uma regra
  compartilhada de cursor sem apagar limites próprios de perfil/raízes.
- **Abrimos mão de:** uma interface única “coletar tudo” no adapter; há objetos
  de página, portas abstratas e coordenação explícita a manter.
- **Risco:** a ordem `yield → checar continuação` afeta parcial e detecção de
  loop; mudar essa ordem pode perder itens ou produzir chamadas extras.
- **Revisitar quando:** uma necessidade confirmada de streaming público,
  retomada ou outro mecanismo de paginação não couber no contrato atual. Isso
  exige avaliação de contrato, não generalização especulativa.

## Consequências e verificação

Implementação em `src/application/ports/`, `src/application/dtos/pages.py`,
`src/application/pagination.py`, `src/domain/services/pagination.py` e casos de uso.
Testes em `tests/unit/test_pagination.py`, `tests/unit/test_usecases.py`,
`tests/integration/test_collector.py`. Casos de uso não importam adapters concretos.

[RN-003 a RN-005](../business-rules/collection.md) · [Paginação](../flows/pagination.md) ·
[API Python](../reference/api-reference.md) · [Arquitetura](../internals/architecture.md).

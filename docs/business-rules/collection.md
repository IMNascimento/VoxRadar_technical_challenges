[⬅️ Regras de negócio](./README.md) · [🏠 Índice](../README.md)

# ⚖️ Coleta

## RN-001 — Fonte por operação

- **Regra:** busca usa a API web; perfil, comentários e respostas usam a API
  móvel. Não há seleção automática de outra superfície após uma falha.
- **Motivação:** preservar os caminhos de coleta implementados e a operação sem
  login, navegador ou runtime de assinatura externo.
- **Implementada em:** `src/infrastructure/container/container.py`, `src/infrastructure/kwai/web/`,
  `src/infrastructure/kwai/mobile/` (cliente e adapter de cada API).
- **Exceções:** fallback móvel troca gateway, não migra para web, SSR ou browser.
- **Verificação:** `tests/integration/test_collector.py`, `tests/integration/test_mobile_api.py`.

## RN-002 — Limite de busca

- **Regra:** na CLI, o limite é inteiro ≥ 1 e padrão 20. Cada palavra processada
  pede `count=min(limit, 50)`; o resultado final contém no máximo `limit`
  postagens únicas, e palavras restantes não são consultadas após atingir o teto.
  `SearchCommand` rejeita a lista vazia e qualquer palavra-chave em branco
  antes de consultar a API, inclusive em chamadas Python.
- **Motivação:** separar tamanho do lote externo do teto agregado solicitado.
- **Implementada em:** `src/application/use_cases/search_posts.py`, `src/entrypoints/cli/app.py`.
- **Exceções:** não existe paginação por cursor na busca; `limit > 50` não gera
  outra página da mesma palavra. A API Python não repete a validação `min=1` da CLI.
- **Verificação:** `tests/unit/test_usecases.py`, `tests/integration/test_collector.py`, `tests/integration/test_cli.py`.

## RN-003 — Limite de perfil e de raízes

- **Regra:** perfil conta postagens únicas; comentários contam raízes cruas,
  antes do dedupe. Sem limite explícito, ambos continuam até o fim da paginação.
  Perfil pede 30 por página; raízes pedem 50.
- **Motivação:** manter as semânticas próprias dos casos de uso, sem unificá-las
  artificialmente ao compartilhar a paginação.
- **Implementada em:** `src/application/use_cases/collect_user_posts.py`,
  `src/application/use_cases/collect_comment_versions.py`.
- **Exceções:** duas raízes repetidas podem consumir limite 2 e produzir apenas
  uma raiz única. A CLI valida limite positivo; casos de uso Python não o fazem.
- **Verificação:** `tests/unit/test_usecases.py`, `tests/integration/test_collector.py`.

## RN-004 — Identidade e deduplicação

- **Regra:** postagens usam id truthy ou URL como chave. Comentários usam id
  truthy; sem id, usam comprimento do id do autor + autor + texto. A primeira
  ocorrência é mantida. A expansão compartilha seu conjunto de respostas vistas.
- **Motivação:** páginas podem se sobrepor; a chave sem id evita colisão causada
  por delimitadores presentes no autor/texto.
- **Implementada em:** `dedup_key` de `Post` e `Comment` (`src/domain/entities/`)
  e `UniqueItems` (`src/domain/services/identity.py`); os casos de uso só
  escolhem quando compartilhar a instância. Na expansão, todas as raízes são
  registradas antes das respostas: resposta com a identidade de uma raiz é descartada.
- **Exceções:** conteúdo idêntico e sem id pode representar comentários distintos
  que essa política funde. Não há dedupe persistido entre execuções.
- **Verificação:** `tests/unit/test_usecases.py`, `tests/unit/test_domain.py`.

## RN-005 — Fim de paginação

- **Regra:** começar com cursor vazio; após entregar uma página, encerrar se a
  página mapeada estiver vazia ou a continuação for vazia. O adapter móvel
  traduz os sentinelas de fim do Kwai (`no_more`, `nomore`, `-1`, `0`) para
  continuação vazia. Continuação já vista gera `RepeatedCursorError`.
- **Motivação:** obedecer à continuação recebida e evitar loops sem fabricar índices.
- **Implementada em:** `src/domain/services/pagination.py` (decisão pura),
  `src/application/pagination.py` (coordenação), `src/domain/value_objects/cursor.py`,
  `src/infrastructure/kwai/http_utils.py` (`read_cursor`).
- **Exceções:** a primeira busca acontece apesar do cursor inicial vazio. O
  consumidor pode parar ao atingir o limite antes de observar uma repetição.
  Página com todos os feeds descartados pelo mapper é vazia para essa regra.
- **Verificação:** `tests/unit/test_pagination.py`, `tests/unit/test_usecases.py`,
  `tests/unit/test_kwai_protocol.py`.

## RN-006 — Expansão de respostas é opt-in

- **Regra:** com `CommentVersions.ROOTS`, retornar raízes `Comment`. Com `REPLIES` ou `ALL`,
  terminar primeiro a coleta de raízes e depois expandi-las. Raiz sem id ou
  com total declarado `None`/zero não consulta sublista. Respostas não consomem
  o limite de raízes, e a sublista pede 100 itens por página.
- **Motivação:** preservar a saída simples e tornar explícito o custo adicional.
- **Implementada em:** `src/domain/services/replies.py` (`declares_replies`),
  `src/application/use_cases/collect_comment_versions.py`, `src/domain/entities/comment.py`.
- **Exceções:** a elegibilidade usa truthiness; total negativo é truthy e pode
  provocar consulta, embora não seja comparado pelo warning de contagem.
- **Verificação:** `tests/unit/test_usecases.py`, `tests/integration/test_mobile_api.py`.

## Relacionados

| Documento | Relação |
|---|---|
| [Busca](../flows/search.md) | RN-001, RN-002, RN-004. |
| [Perfil](../flows/profile.md) | RN-001, RN-003, RN-004, RN-005. |
| [Comentários](../flows/comments.md) | RN-001, RN-003 a RN-006. |
| [Portas e paginação](../adr/0003-page-ports-and-pagination.md) | Compartilhamento sem apagar diferenças de limite. |

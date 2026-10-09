[⬅️ Regras de negócio](./README.md) · [🏠 Índice](../README.md)

# ⚖️ Falhas e resultado parcial

## RN-011 — Retry não corrige erro de negócio

- **Regra:** erro de negócio não nulo e diferente de `1` gera `KwaiApiError`,
  sem retry ou troca de gateway. Falhas de transporte seguem a política web ou
  a escada móvel, com `max_retries` tentativas/rodadas extras e backoff de 0,5 a 8 s.
- **Motivação:** distinguir uma resposta recebida de uma tentativa de transporte falha.
- **Implementada em:** `src/infrastructure/kwai/business_result.py`,
  `src/infrastructure/kwai/web/client.py`, `mobile/client.py`, `http_utils.py`.
- **Exceções:** `result` ausente/nulo é tolerado; a comparação não é estrita de
  tipo. JSON não-objeto móvel entra no fallback; erro interno de lista/cursor, não.
- **Verificação:** `tests/integration/test_mobile_api.py`, `tests/integration/test_collector.py`,
  `tests/integration/test_response_validation.py`.

## RN-012 — Página de comentários inválida é rejeitada inteira

- **Regra:** `rootComments`, `subComments` e `users`, se presentes/não nulos,
  devem ser listas de objetos. Lista ou item inválido gera
  `UnexpectedResponseError` antes de entregar a página; não pular silenciosamente
  um item de comentários para fazer o lote parecer completo.
- **Motivação:** não ocultar perda dentro da página. Páginas anteriores são
  preservadas pela política de interrupção, quando há itens.
- **Implementada em:** `src/infrastructure/kwai/http_utils.py`, `mobile/client.py`.
- **Exceções:** ausente/nulo vira lista vazia. Feeds têm política distinta:
  item não-objeto é ignorado; feed sem URL montável é ignorado com warning.
- **Verificação:** `tests/integration/test_response_validation.py`, `tests/unit/test_parsers.py`.

## RN-013 — Preservar itens antes de interromper

- **Regra:** falha `KwaiCollectorError` coberta pelo caso de uso, com itens já
  coletados, vira `CollectionInterruptedError`, com tupla `partial` e causa
  original em `__cause__`. Sem itens, propaga a causa original.
- **Motivação:** não descartar o lote anterior nem representar uma coleta
  interrompida como sucesso completo.
- **Implementada em:** `src/application/exceptions.py` e os três casos de uso.
- **Exceções:** não engloba toda exceção Python inesperada. Durante expansão,
  falha de sublista mantém também as raízes ainda não expandidas; não continua
  tentando suas respostas depois dessa falha.
- **Verificação:** `tests/unit/test_usecases.py`, `tests/integration/test_response_validation.py`.

## RN-014 — Loop de sublista não impede a próxima raiz

- **Regra:** repetição de continuação em sublista gera warning local, preserva
  respostas entregues e continua com outra raiz. Repetição em perfil/raízes
  interrompe essa coleta, seguindo a regra de parcial.
- **Motivação:** manter a política existente de isolamento do loop de uma raiz.
- **Implementada em:** `src/domain/services/pagination.py`, `collect_comment_versions.py`.
- **Exceções:** transporte/estrutura inválida de sublista não usa essa
  recuperação local; interrompe com parcial. A página é entregue antes da
  checagem de continuação, podendo contribuir itens antes de o loop ser acusado.
- **Verificação:** `tests/unit/test_pagination.py`, `tests/unit/test_usecases.py`.

## RN-015 — Persistência e código de saída são distintos

- **Regra:** CLI tenta escrever o parcial e sai com `1`; entrada inválida
  reconhecida sai com `2`; execução sem erro sai com `0`. Falha `OSError` ao
  escrever parcial é registrada e mantém `1`. Os arquivos JSON são UTF-8.
- **Motivação:** permitir ao consumidor separar sucesso, erro e parcial por
  sinal operacional, sem acrescentar um envelope ao contrato JSON.
- **Implementada em:** `src/entrypoints/cli/app.py`, `export_commands.py`, `export_files.py`.
- **Exceções:** falha sem itens não publica JSON. Os comandos criam uma execução
  exclusiva e publicam cada JSON por rename, com `.partial.json` para parciais.
  Não há transação do conjunto; erro de uma unidade não impede as outras.
  Exit `0` não prova completude; warning numérico sozinho não muda esse código.
- **Verificação:** `tests/integration/test_cli.py`, `tests/integration/test_cli_exports.py`. Veja [CLI](../guides/cli.md).

## Relacionados

[Paginação e interrupção](../flows/pagination.md) · [Ciclo de vida](../flows/runtime.md) ·
[Manutenção](../maintenance/maintenance.md) · [ADR de parcial](../adr/0004-partial-results-and-declared-counts.md).

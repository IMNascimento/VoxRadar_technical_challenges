[⬅️ Regras de negócio](./README.md) · [🏠 Índice](../README.md)

# ⚖️ Contrato de dados

## RN-007 — Saída tipada e nomes estáveis

- **Regra:** a saída normal é lista de `Post` ou `Comment`; com expansão, os
  itens são `ExpandedComment`. Modelos rejeitam campos extras; campos JSON
  continuam em português. A CLI serializa por `dataclasses.asdict()` sem excluir nulos.
- **Motivação:** manter um contrato de consumo separado do payload da plataforma.
- **Implementada em:** `src/domain/entities/`, `src/entrypoints/cli/export_files.py`.
- **Exceções:** um parcial da etapa de raízes ainda é `Comment`, mesmo se a
  execução pediu expansão. Modelos não são validadores estritos de todo dado cru.
- **Verificação:** `tests/unit/test_models.py`, `tests/unit/test_samples.py`, `tests/integration/test_cli.py`.

## RN-008 — Desconhecido não é zero

- **Regra:** métrica ausente/não conversível fica `None`, serializada como
  `null`; zero só é produzido quando a conversão da entrada resulta em zero.
  `as_int_scalar` aceita int/float/string, rejeita bool/estruturas e captura
  `TypeError`, `ValueError`, `OverflowError`.
- **Motivação:** não confundir falta de dado com contagem zerada.
- **Implementada em:** `src/infrastructure/kwai/coercion.py`, `src/infrastructure/kwai/mapping.py`.
- **Exceções:** `int()` trunca float finito (`3.9 → 3`); não há mínimo zero nos
  modelos. Strings opcionais e fallback `caption → user_text` têm limitações
  semânticas detalhadas em [Schemas](../reference/schemas.md), não resolvidas por esta regra.
- **Verificação:** `tests/unit/test_kwai_protocol.py`, `tests/unit/test_parsers.py`, `tests/integration/test_response_validation.py`.

## RN-009 — Carimbo de coleta e datas

- **Regra:** cada execução gera um `coletado_em` comum aos itens. Timestamps
  externos positivos são convertidos de milissegundos para UTC com precisão de
  segundos e sufixo `Z`; ausentes, inválidos ou fora do intervalo viram `None`.
- **Motivação:** distinguir data do conteúdo do momento da coleta e padronizar a saída.
- **Implementada em:** `src/domain/value_objects/iso_timestamp.py` (formato),
  `src/infrastructure/kwai/coercion.py` (milissegundos), `SystemClock`, casos de uso e `mapping.py`.
- **Exceções:** campos de data dos modelos são strings; construir um modelo
  manualmente não valida calendário. `IsoTimestamp` valida formato, calendário e
  horário; `from_datetime` rejeita instantes sem fuso definido.
- **Verificação:** `tests/unit/test_parsers.py`, `tests/unit/test_domain.py`.

## RN-010 — Total declarado não significa completude

- **Regra:** na raiz expandida, `respostas_total` conserva `sub_comment_count`
  convertido. Quando o total é conhecido e não negativo, comparar com respostas
  únicas entregues nessa expansão; divergência para mais ou menos gera warning
  com “causa não determinada”, sem mudar JSON, retry ou exit code.
- **Motivação:** tornar a diferença observável sem inventar itens ou uma causa.
- **Implementada em:** `src/domain/services/replies.py` (`replies_diverge`),
  `src/infrastructure/kwai/mobile/adapter.py`,
  `src/application/use_cases/collect_comment_versions.py`, `src/domain/entities/comment.py`.
- **Exceções:** total desconhecido/negativo não é comparado. Aviso também pode
  ocorrer durante falha ou em raiz sem id consultável. As 59 declaradas e 52
  entregues do experimento são observação de um alvo, não uma proporção universal.
- **Verificação:** `tests/unit/test_domain.py`, `tests/unit/test_usecases.py`,
  `tests/integration/test_mobile_captures.py`.

## Relacionados

[Schemas](../reference/schemas.md) · [Comentários](../flows/comments.md) ·
[ADR de parcial e contagens](../adr/0004-partial-results-and-declared-counts.md).

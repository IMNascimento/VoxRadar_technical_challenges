[⬅️ Regras de negócio](./README.md) · [🏠 Índice](../README.md)

# ⚖️ Contrato de dados

## RN-008 — Saída validada por modelos

- **Regra:** a saída é uma lista de `Post` ou `Comment`; com `--with-replies`,
  de `CommentWithReplies`. Todo item passa pelo construtor do modelo Pydantic,
  que exige os campos obrigatórios e valida os tipos e o formato das datas. Os
  campos JSON ficam em português, com os nomes do desafio. A CLI serializa com
  `model_dump()`, sem omitir nulos.
- **Motivação:** garantir que o JSON sempre siga os schemas `Postagem` e
  `Comentario`, independente do payload do Kwai.
- **Implementada em:** [`models.py`](../../kwai_collector/models.py),
  [`parser.py`](../../kwai_collector/parser.py), `collect_and_save` em
  [`cli.py`](../../kwai_collector/cli.py).
- **Exceções:** campos extras passados ao construtor são ignorados, não
  rejeitados. Um dado que não caiba no modelo levanta `ValidationError`, que a
  CLI não trata.
- **Verificação:** `tests/test_parser.py`, `tests/test_samples.py`.

## RN-009 — Desconhecido não é zero

- **Regra:** métrica ausente ou não conversível fica `None` e sai como `null`.
  Zero só aparece quando a API mandou um valor que converte para zero.
  `to_int` aceita int, float e string, rejeita `bool` e devolve `None` em
  `TypeError`, `ValueError` ou `OverflowError`.
- **Motivação:** não confundir falta de dado com contagem zerada, como pede o
  schema do desafio.
- **Implementada em:** `to_int` e `parse_post` em `parser.py`.
- **Exceções:** `int()` trunca float finito (`3.9 → 3`); a string `"3.9"` vira
  `None`. Os modelos não impõem mínimo zero.
- **Verificação:** `tests/test_parser.py` (`test_metrica_ausente_fica_none`,
  `test_to_int_e_ms_to_iso`).

## RN-010 — Datas e carimbo de coleta

- **Regra:** cada comando gera um único `coletado_em`, no início da coleta,
  usado em todos os itens. Timestamps do Kwai positivos são convertidos de
  milissegundos para UTC com precisão de segundos e sufixo `Z`; ausentes, zero,
  negativos ou inválidos viram `None`. Os modelos rejeitam data fora do formato
  `AAAA-MM-DDTHH:MM:SSZ`.
- **Motivação:** separar a data do conteúdo do momento da coleta e padronizar
  a saída em ISO-8601.
- **Implementada em:** `now_iso` e `ms_to_iso` em `parser.py`; `ISO_DATE` em
  `models.py`.
- **Exceções:** o padrão valida o formato, não o calendário (`2026-02-31` passaria
  pela regex, embora o parser nunca gere essa data).
- **Verificação:** `tests/test_parser.py` (`test_to_int_e_ms_to_iso`,
  `test_modelo_rejeita_data_fora_do_padrao`).

## RN-011 — Total declarado não significa completude

- **Regra:** no comentário principal expandido, `respostas_total` guarda o
  `sub_comment_count` devolvido pela API, convertido para inteiro. O coletor não
  ajusta esse número à quantidade de respostas entregues.
- **Motivação:** expor a diferença sem inventar itens nem uma causa.
- **Implementada em:** `get_root_comments` e `get_comments` em `scraper.py`.
- **Exceções:** o coletor não registra warning quando o total declarado diverge
  do entregue; compare `respostas_total` com a contagem de itens que têm aquele
  `parent_id`. Em verificações, um comentário declarava 59 respostas e a API
  entregou 52 antes de indicar o fim.
- **Verificação:** `tests/test_cli.py` (`test_comments_com_respostas`, que confere
  `respostas_total == 59` com três respostas na fixture).

## Relacionados

[Schemas](../reference/schemas.md) · [Comentários](../flows/comments.md) ·
[ADR-0005 — Modelos Pydantic](../adr/0005-pydantic-output-models.md).

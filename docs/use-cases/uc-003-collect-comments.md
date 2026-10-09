[⬅️ Casos de uso](./README.md) · [🏠 Índice](../README.md)

# 🎯 UC-003 — Coletar comentários e respostas

| | |
|---|---|
| **Ator** | Usuário da CLI ou programa Python chamador. |
| **Objetivo** | Obter raízes de uma postagem e, opcionalmente, respostas com vínculo explícito. |
| **Pré-condições** | Configuração válida, acesso HTTPS aos gateways e string com `/video/<id>` ou `/photo/<id>`. |
| **Entrada** | `CommentCollectionCommand.create(post_url, *, limit=None, with_comments=True, with_replies=False)`; CLI `comments --url`, `--with-comments-replies`. |
| **Implementação** | `src/application/use_cases/collect_comment_versions.py`, injetado com `ICommentApiPort`. |
| **Saída** | `CollectionResult` por versão: `Comment`; com expansão concluída, lista plana de `ExpandedComment`. |

## Fluxo principal

1. Extrair `PhotoId` da string de entrada ao criar o comando; gerar `coletado_em` pelo relógio injetado.
2. Paginar raízes com `count=50`, contando itens crus até o limite quando houver.
3. Deduplicar raízes e conservar seus totais declarados separadamente do modelo simples.
4. Sem expansão, devolver os comentários simples.
5. Com expansão, terminar a etapa de raízes e acrescentar uma raiz expandida.
6. Se elegível, paginar suas respostas com `count=100`, deduplicar e inserir
   `parent_id` e informações do usuário respondido.
7. Comparar total declarado conhecido não negativo com quantidade única entregue.
8. Continuar com a próxima raiz; devolver lista plana e serializar na CLI.

`comments` usa `CollectCommentVersions`, que marca a etapa de falha no
resultado. Veja as opções em [CLI](../guides/cli.md).

## Fluxos alternativos

- **1a — Id não extraível:** `InvalidInputError`. A extração não certifica host da URL.
- **2a — Raízes repetidas:** consomem o limite cru, mas não são emitidas repetidamente.
- **2b — Página inválida:** rejeitar inteira; páginas anteriores permanecem no parcial.
- **2c — Raízes interrompidas com expansão solicitada:** parcial de `Comment`;
  não começar a expandir uma etapa de raízes que falhou.
- **6a — Raiz sem id ou total `None`/zero:** não consultar sublista; pode haver
  warning de declarado versus zero se o total conhecido não negativo divergir.
- **6b — Total negativo malformado:** o teste truthy pode consultar sublista;
  o comparador de quantidade ignora total negativo.
- **6c — Cursor de sublista repetido:** warning, preservar respostas lidas e seguir outra raiz.
- **6d — Outra falha de sublista:** interromper; parcial inclui respostas já lidas
  e raízes ainda não expandidas. Não tentar suas respostas após a falha.
- **7a — Contagem diferente:** warning sem atribuir causa, sem retry automático e sem mudar exit code por si só.
- **8a — Escrita parcial falha:** registrar erro, manter exit `1`; persistência não é garantida.

## Pós-condições e limites

- O limite não controla quantidade de respostas nem volume total da expansão.
- `parent_id` aponta para comentário raiz; `reply_to_id` aponta para **usuário**.
- `respostas_total` conserva a declaração da API, não o tamanho da lista de respostas.
- Fim de cursor não comprova completude. Previews embutidos não são mesclados.
- Warning de quantidade não é o mesmo que interrupção. Consumidores devem ler
  também o exit code, pois a lista parcial não inclui envelope de erro.

## Verificação

| Área | Testes |
|---|---|
| Limites crus, expansão, vínculos, loops e total divergente | `tests/unit/test_usecases.py`. |
| Corpo de raízes/sublista e assinatura | `tests/integration/test_mobile_api.py`. |
| Capturas sanitizadas | `tests/integration/test_mobile_captures.py`. |
| Página inválida e parcial | `tests/integration/test_response_validation.py`. |
| CLI e gravação | `tests/integration/test_cli.py`. |

## Relacionados

[Fluxo de comentários](../flows/comments.md) · [Paginação](../flows/pagination.md) ·
[RN-003 a RN-006](../business-rules/collection.md) ·
[RN-007 e RN-010](../business-rules/data-contract.md) ·
[RN-012 a RN-015](../business-rules/failure-policy.md) ·
[ADR de parcial/contagens](../adr/0004-partial-results-and-declared-counts.md).

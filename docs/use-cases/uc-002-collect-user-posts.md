[⬅️ Casos de uso](./README.md) · [🏠 Índice](../README.md)

# 🎯 UC-002 — Coletar postagens de um perfil

| | |
|---|---|
| **Ator** | Usuário da CLI ou programa Python chamador. |
| **Objetivo** | Obter posts entregues pela API móvel para um perfil, paginados e deduplicados. |
| **Pré-condições** | Configuração válida, acesso HTTPS aos gateways e handle reconhecido pela validação local. |
| **Entrada** | `user: str`, `limit: int \| None = None`; CLI `--user/-u`. |
| **Implementação** | `src/application/collect_user_posts.py`, injetado com `ProfileApiPort`. |
| **Saída** | `list[Post]`, na ordem do feed após dedupe. |

## Fluxo principal

1. Remover arrobas/espaços de borda e validar `Handle`.
2. Gerar `coletado_em` e resolver o handle em `UserId` via `getInfo`.
3. Começar o feed com cursor vazio e pedir 30 itens com contexto mínimo validado.
4. Receber `ProfilePage`; acumular posts únicos por id/URL.
5. Continuar com o cursor recebido enquanto não houver fim ou limite único atingido.
6. Devolver a lista. Na CLI nova, gravar resultado antes de fechar clientes.

`profile` pode acrescentar versões de comentários por postagem via
`CollectProfileBundle`, sem mudar o retorno de `CollectUserPosts`. Use
`--with-comments`, `--with-comments-replies` ou ambas, e `--comments-limit`
para limitar raízes por postagem. Falha em uma postagem não impede as demais.
Consulte [CLI](../guides/cli.md) para saída por pasta e parciais.

## Fluxos alternativos

- **1a — Handle inválido:** `InvalidInputError`, sem consulta de páginas.
- **2a — Resolução vazia/sem id válido:** erro da resolução; nenhum parcial de posts.
- **3a — Gateways falham no transporte:** tentar escada e rodadas extras configuradas.
- **3b — Erro de negócio:** abortar sem fallback/retry de negócio.
- **4a — Página mapeada vazia:** encerrar; pode ser efeito de feeds descartados,
  não necessariamente ausência de conteúdo cru no payload.
- **5a — Limite alcançado:** parar de consumir sem pedir página extra.
- **5b — Cursor repetido ou falha posterior:** interromper com posts acumulados em parcial.
- **6a — Escrita falha:** a CLI sinaliza exit `1`; o chamador Python escolhe sua política de I/O.

## Pós-condições e limites

- Sem limite, o término segue a API e a paginação compartilhada, não uma prova
  de coleta de todos os posts existentes.
- Não há SSR, Nuxt, sessão de navegador ou rota web de fallback.
- O contexto completo também entregou feeds no app observado. Usar o mínimo
  no coletor não estabelece proibição universal do completo.
- Sem checkpoint: outra execução resolve usuário e pagina do início novamente.

## Verificação

| Área | Testes |
|---|---|
| Resolução, limite único, dedupe e parcial | `tests/test_usecases.py`. |
| Contexto e corpo por rota | `tests/test_mobile_api.py`. |
| Capturas reais sanitizadas e mapeamento | `tests/test_mobile_captures.py`. |
| Composição com HTTP simulado | `tests/test_collector.py`. |

## Relacionados

[Fluxo de perfil](../flows/profile.md) · [Paginação](../flows/pagination.md) ·
[RN-001, RN-003 a RN-005](../business-rules/collection.md) ·
[RN-013](../business-rules/failure-policy.md) ·
[ADR móvel](../adr/0001-mobile-profile-and-comments.md) · [Assinatura](../internals/signature.md).

[⬅️ Fluxos](./README.md) · [🏠 Índice](../README.md)

# 🔀 Fluxo — Busca de postagens

> **Resumo:** paginar cada palavra-chave em sequência, mapear feeds e entregar
> uma lista deduplicada com limite total.

```mermaid
flowchart LR
    Input[Lista de palavras] --> Count[Definir count entre 1 e 50]
    Count --> Word[Próxima palavra]
    Word --> Web[POST web sem sig]
    Web --> Map[Mapear feeds]
    Map --> Dedup[Deduplicar por id ou URL]
    Dedup --> Limit{Limite total atingido?}
    Limit -->|Sim| Output[Lista limitada de Post]
    Limit -->|Não| New{Veio post novo?}
    New -->|Sim| Next[pcursor += count]
    Next --> Web
    New -->|Não, há palavra| Word
    New -->|Não, fim| Output
```

## Etapas

1. **Validar e preparar:** `SearchPosts.execute` rejeita lista vazia; calcula
   `count` uma vez a partir do limite total, não do saldo entre palavras.
2. **Consultar:** `KwaiWebAdapter.search_page` envia JSON para
   `/rest/o/w/pwa/v2/search/word/outer` com o `pcursor` da página, com retry de
   transporte selecionado, e devolve o deslocamento da próxima página.
3. **Mapear:** `parse_feeds` aplica o contrato e a política de itens de feed.
4. **Deduplicar:** `SearchPosts` conserva a primeira ocorrência por id truthy ou URL.
5. **Paginar:** se a página trouxe post novo e o limite não foi atingido, pede
   a próxima página da mesma palavra; sem post novo, passa para a próxima palavra.
6. **Parar:** ao atingir o limite, não pede mais páginas nem consulta palavras
   restantes; fatia o resultado ao teto.
7. **Falhar:** erro de uma palavra posterior preserva itens das anteriores em parcial.

A API não devolve cursor de continuação nem lista vazia: quando a palavra se
esgota, repete itens já entregues. Por isso o fim de cada palavra é a primeira
página sem post novo.

## Regras envolvidas

[RN-001, RN-002 e RN-004 — fonte, limite e identidade](../business-rules/collection.md) ·
[RN-008 — conversão](../business-rules/data-contract.md#rn-008--desconhecido-não-é-zero) ·
[RN-011 e RN-013 — retry e parcial](../business-rules/failure-policy.md).

## Referências

[UC-001](../use-cases/uc-001-search-posts.md) · [Schemas](../reference/schemas.md) ·
[Protocolo e resiliência](../internals/mobile-api.md).

Verificação: `tests/unit/test_usecases.py`, `tests/integration/test_collector.py`.

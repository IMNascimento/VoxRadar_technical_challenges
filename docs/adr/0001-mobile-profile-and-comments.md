[⬅️ ADRs](./README.md) · [🏠 Índice](../README.md)

# ADR-0001 — Usar API móvel para perfil e comentários

| | |
|---|---|
| **Status** | ✅ Aceita — adotada no código examinado. |
| **Data** | 2026-10-08 — registro retrospectivo, não data original comprovada. |
| **Escopo** | Fontes de perfil/comentários; busca permanece web. |

## Contexto

A coleta deve executar sem login, cookies fornecidos, browser, emulador ou
Frida em runtime. A coleta inicial de perfil por SSR não oferecia a paginação
implementada hoje. Chamadas web anônimas examinadas não entregaram a paginação
de perfil/lista de comentários desejadas. A API móvel foi observada entregando
esses dados com assinatura calculada localmente.

## Alternativas

**A — Web/SSR:** aproveitava dados embutidos e requisições web; o caminho anterior
de perfil ficava restrito à página inicial e não atendia à paginação desejada.
Chamadas web examinadas de comentários não entregaram a lista anônima esperada.

**B — Browser/sessão ou automação de app:** pode auxiliar investigação, mas
introduz infraestrutura e, em caminhos autenticados, altera o requisito anônimo.
Não é fallback disponível no pacote atual.

**C — API móvel anônima:** permite resolução de handle e paginação por cursor;
exige manter contexto, assinatura, gateways e formatos externos.

## Decisão

Manter busca no adapter web e usar `MobileApiAdapter` para perfil e comentários.
Perfil segue `getInfo → feed/profile`; comentários seguem listagem de raízes e
sublista opcional. Não restaurar Nuxt nem adicionar fallback web silencioso.

O contexto do feed permanece mínimo validado; não se registra aqui uma regra
de rejeição universal do contexto completo, pois o app também entregou feeds com ele.

## Trade-offs

- **Ganhamos:** paginação de perfil no fluxo Python, coleta anônima observada e
  remoção do parser SSR e do custo operacional de browser.
- **Abrimos mão de:** fonte embutida no HTML como alternativa de runtime;
  assumimos dependência em endpoints móveis sem contrato oficial estável.
- **Risco:** uma resposta válida hoje não garante compatibilidade futura,
  completude ou acesso sob outro build/região/contexto.
- **Revisitar quando:** protocolo móvel deixar de atender às operações e houver
  evidência de outra superfície compatível com os requisitos. Não migrar para
  login ou automação pesada sem decisão explícita de produto/arquitetura.

## Consequências e verificação

Implementada em `src/container.py`, `src/infrastructure/mobile_client.py` e
`src/application/collect_user_posts.py`. Testes: `test_mobile_api.py`,
`test_collector.py`, `test_usecases.py`, todos em `tests/`.

[RN-001](../business-rules/collection.md#rn-001--fonte-por-operação) ·
[Fluxo de perfil](../flows/profile.md) · [UC-002](../use-cases/uc-002-collect-user-posts.md) ·
[Pesquisa](../maintenance/research.md).

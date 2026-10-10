[⬅️ ADRs](./README.md) · [🏠 Índice](../README.md)

# ADR-0001 — Usar a API móvel para perfil e comentários

| | |
|---|---|
| **Status** | ✅ Aceita — adotada no código atual. |
| **Data** | 2026-10-09 — registro retrospectivo. |
| **Escopo** | Fontes de perfil e comentários; a busca continua na web. |

## Contexto

A coleta precisa rodar sem login, sem cookies, sem navegador, sem emulador e
sem Frida. A busca web responde em JSON e atende à funcionalidade de busca.
Já o perfil embutido no HTML do site só trazia a primeira página, e as chamadas
web anônimas examinadas não entregaram a paginação do perfil nem a lista de
comentários. A API móvel do Kwai Lite entregou esses dados com uma assinatura
calculada localmente.

## Alternativas

**A — Web e HTML do site (SSR):** reaproveita dados embutidos e requisições web;
o perfil ficava restrito à página inicial e os comentários anônimos não vieram.

**B — Navegador ou automação do app:** ajuda na investigação, mas traz
infraestrutura pesada e, em caminhos autenticados, quebra o requisito de
coleta anônima.

**C — API móvel anônima:** resolve o usuário em id e pagina por cursor; exige
manter contexto, assinatura, hosts e formatos externos.

## Decisão

Usar `post_web` para a busca e `post_mobile` para perfil e comentários. Perfil
segue `getInfo → feed/profile`; comentários seguem `comment/list/v2` e,
opcionalmente, `comment/sublist`. Não há fallback para HTML nem para navegador.

O feed de perfil usa o contexto mínimo validado (`kpn`, `appver`). Isso não
registra uma rejeição universal do contexto completo, que também já funcionou
no app.

## Trade-offs

- **Ganhamos:** perfil paginado até o fim, comentários e respostas anônimos e
  nenhum parser de HTML nem navegador no projeto.
- **Abrimos mão de:** uma fonte de dados embutida no HTML como alternativa;
  passamos a depender de endpoints móveis sem contrato oficial.
- **Risco:** uma resposta válida hoje não garante compatibilidade futura,
  completude ou acesso em outra versão, região ou contexto.
- **Revisitar quando:** o protocolo móvel deixar de atender às operações e
  houver outra superfície compatível com a coleta anônima. Não migrar para
  login ou automação pesada sem decisão explícita.

## Consequências e verificação

Implementada em [`client.py`](../../kwai_collector/client.py) e
[`scraper.py`](../../kwai_collector/scraper.py). Testes: `tests/test_cli.py` e
`tests/test_client.py`.

[RN-001](../business-rules/collection.md#rn-001--fonte-por-operação) ·
[Fluxo de perfil](../flows/profile.md) · [UC-002](../use-cases/uc-002-collect-user-posts.md) ·
[Pesquisa](../maintenance/research.md).

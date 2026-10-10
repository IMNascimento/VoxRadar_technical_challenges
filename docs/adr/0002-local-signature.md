[⬅️ ADRs](./README.md) · [🏠 Índice](../README.md)

# ADR-0002 — Calcular `sig` localmente em Python

| | |
|---|---|
| **Status** | ✅ Aceita — adotada no código atual. |
| **Data** | 2026-10-09 — registro retrospectivo. |
| **Escopo** | Assinatura das rotas móveis usadas, não de todas as rotas do app. |

## Contexto

As requisições observadas funcionaram sem `__NS_sig3`. O `sig` foi reproduzido
como MD5 dos parâmetros canonicalizados mais o sal da versão de referência do
app. A coleta não deve precisar do app rodando nem de serviço de terceiros.

## Alternativas

**A — Assinar usando o app via Frida:** útil como instrumento de comparação,
mas exige dispositivo ou emulador e um processo externo durante a coleta.

**B — Emular a biblioteca nativa (Unidbg):** caminho pesquisado; o protótipo
para a versão alvo não gerou assinatura utilizável. Traria JVM, binários e
compatibilidade de ambiente sem necessidade comprovada.

**C — Fórmula local validada:** sem dependências de runtime e com vetor de
regressão independente; exige manter a canonicalização e a identidade do app.

## Decisão

Usar `create_signature` em [`client.py`](../../kwai_collector/client.py), com
`APP_VERSION`, `CLIENT_KEY` e `SIG_SALT` no mesmo módulo. Combinar query e
corpo, excluir exatamente `sig`, `__NS_sig3` e `__NStokensig`, ordenar as chaves,
concatenar sem separador e acrescentar `SIG_SALT` antes do MD5. Não implementar
`sig3`.

Isso não afirma que MD5 seja indicado para autenticação nova, nem que um match
recupere um sal desconhecido.

## Trade-offs

- **Ganhamos:** execução em Python puro, sem dispositivo nem JVM, e cálculo
  determinístico testável offline.
- **Abrimos mão de:** delegar ao app futuras mudanças do assinador; a
  implementação local precisa de nova prova quando a versão ou o protocolo
  mudar.
- **Risco:** o sal validado para uma versão não garante outra (com `appver` 13.7
  a API respondeu `result: 50`).
- **Revisitar quando:** houver evidência reproduzível de mudança de fórmula ou
  exigência nova de assinatura.

## Consequências e verificação

Não há variável de ambiente para trocar o sal. Mudar a versão exige validar o
conjunto e atualizar o vetor real em `tests/test_client.py`
(`test_sig_igual_ao_do_app`).

[Assinatura](../internals/signature.md) · [Protocolo móvel](../internals/mobile-api.md) ·
[Manutenção](../maintenance/maintenance.md).

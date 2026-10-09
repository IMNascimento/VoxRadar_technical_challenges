[⬅️ ADRs](./README.md) · [🏠 Índice](../README.md)

# ADR-0002 — Calcular `sig` localmente em Python

| | |
|---|---|
| **Status** | ✅ Aceita — adotada no código examinado. |
| **Data** | 2026-10-08 — registro retrospectivo, não data original comprovada. |
| **Escopo** | Assinatura das operações móveis atuais, não todas as rotas do app. |

## Contexto

Requests observados funcionaram sem `__NS_sig3`. O `sig` foi reproduzido por
MD5 de parâmetros canonicalizados mais o sal da identidade de referência.
O runtime não deve precisar do app ou de serviço pronto de terceiros.

## Alternativas

**A — Reutilizar o app via Frida:** útil como instrumento de comparação no
laboratório, mas exige processo/dispositivo e lifecycle externo na execução.

**B — Emular biblioteca nativa com Unidbg:** caminho pesquisado; o protótipo do
build alvo não gerou assinatura utilizável. Acrescentaria JVM, binários e
compatibilidade de ambiente sem necessidade comprovada para as rotas atuais.

**C — Fórmula local validada:** reduz runtime e permite vetor de regressão
independente; assume manutenção de canonicalização e identidade do app.

## Decisão

Usar `src/infrastructure/signature.py`, com identidade em `app_identity.py`.
Combinar query/corpo, excluir exatamente `sig`, `__NS_sig3`, `__NStokensig`,
ordenar chaves, concatenar sem separadores e acrescentar `SIG_SALT` antes do MD5.
Não implementar `sig3` nem inserir daemon/`.so` na coleta.

Isso não afirma que MD5 seja indicado para autenticação nova, nem que um match
recupere um sal desconhecido. `atlasSign(path + sig)` não é fórmula comprovada.

## Trade-offs

- **Ganhamos:** execução Python sem device/JVM, cálculo determinístico testável
  offline e menos recursos externos para gerenciar.
- **Abrimos mão de:** delegar futuras mudanças do assinador à execução do app;
  a implementação local precisa de nova prova quando a identidade/protocolo mudar.
- **Risco:** sal/contexto validado para um build não garante outro; a fórmula
  não reproduz toda a segurança, fingerprint ou autorização do app.
- **Revisitar quando:** evidência reproduzível mostrar mudança de fórmula ou
  requisito novo de assinatura. Avaliar o requisito antes de adicionar um
  assinador externo que mude o contrato operacional.

## Consequências e verificação

Não existe variável de `.env` para trocar sal automaticamente. Alterar versão
exige validar o conjunto e o vetor real independente em `tests/test_mobile_api.py`.
Capturas de laboratório não entram no runtime.

[Assinatura](../internals/signature.md) · [Protocolo móvel](../internals/mobile-api.md) ·
[RN-001](../business-rules/collection.md#rn-001--fonte-por-operação) ·
[Manutenção](../maintenance/maintenance.md).

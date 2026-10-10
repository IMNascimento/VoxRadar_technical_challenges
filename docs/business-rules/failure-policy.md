[⬅️ Regras de negócio](./README.md) · [🏠 Índice](../README.md)

# ⚖️ Falhas e saída

## RN-012 — Entrada inválida é rejeitada antes da rede

- **Regra:** antes de qualquer requisição, a coleta rejeita com `InvalidInput`:
  busca sem nenhuma palavra-chave válida; usuário que, depois de remover espaços
  e `@` do início, fique vazio ou contenha espaço, `/` ou `@`; URL sem
  `/video/<id>` ou `/photo/<id>`. A CLI também rejeita opções fora do esperado,
  como `--limit 0`.
- **Motivação:** falhar rápido, com mensagem clara, sem gastar requisições.
- **Implementada em:** `search_posts`, `get_user_posts` e `get_photo_id` em
  [`scraper.py`](../../kwai_collector/scraper.py); `min=1` nas opções de
  [`cli.py`](../../kwai_collector/cli.py).
- **Exceções:** a validação da URL não confere o host: qualquer texto com
  `/video/<número>` é aceito. Usuário inexistente só é detectado pela API
  (exit `1`, não `2`).
- **Verificação:** `tests/test_cli.py` (`test_url_invalida_sai_com_2`).

## RN-013 — Retry só em falha passageira

- **Regra:** são passageiras as falhas de transporte do HTTPX, os status `429`,
  `500`, `502`, `503`, `504` e a resposta que não é objeto JSON. Elas são
  repetidas até `max_retries` vezes extras, com espera de 0,5 s dobrando a cada
  tentativa até o teto de 8 s. Os demais status de erro não são repetidos: na
  busca viram `KwaiError` na hora; na API móvel passam para o próximo host e, se
  todos os hosts falharem só com esse tipo de erro, viram `KwaiError` sem nova
  rodada.
- **Motivação:** insistir quando a falha pode passar e desistir logo quando
  repetir não muda o resultado (ex.: `403`).
- **Implementada em:** `post_json`, `with_retry`, `post_web` e `post_mobile` em
  [`client.py`](../../kwai_collector/client.py).
- **Exceções:** HTML de CDN no lugar do JSON conta como passageiro também na
  busca web.
- **Verificação:** `tests/test_client.py` (`test_tenta_o_proximo_host_quando_um_falha`,
  `test_desiste_depois_dos_retries`, `test_erro_4xx_nao_tenta_de_novo`).

## RN-014 — Erro de negócio não é repetido

- **Regra:** o Kwai pode responder `HTTP 200` com erro no campo `result`. Se
  `result` existir e for diferente de `1`, a resposta vira `KwaiError` com a
  mensagem `error_msg`, o código e a rota. Não há retry nem troca de host.
- **Motivação:** um erro de negócio (assinatura rejeitada, parâmetro errado) se
  repete igual em qualquer host e em qualquer tentativa.
- **Implementada em:** `check_result` em `client.py`.
- **Exceções:** `result` ausente ou nulo é aceito como sucesso.
- **Verificação:** `tests/test_client.py` (`test_erro_de_negocio_nao_tenta_de_novo`).

## RN-015 — Saída tudo ou nada

- **Regra:** os itens ficam em memória até a coleta terminar. Se qualquer erro
  interromper a coleta, nada é gravado nem impresso: os itens já obtidos são
  descartados e o comando sai com código `1`. Um arquivo que já existia no
  destino não é alterado.
- **Motivação:** manter o código simples e nunca entregar um arquivo incompleto
  que pareça completo.
- **Implementada em:** `collect_and_save` em `cli.py`, que só escreve depois de
  `collect()` retornar.
- **Exceções:** sem checkpoint nem retomada: uma nova execução começa do zero.
  O custo dessa escolha está na [ADR-0004](../adr/0004-all-or-nothing-output.md).
- **Verificação:** `tests/test_cli.py` (`test_erro_de_rede_sai_com_1`).

## RN-016 — Códigos de saída e escrita

- **Regra:** `0` quando a coleta termina e o JSON é entregue; `1` quando há
  `KwaiError` ou falha ao gravar o arquivo (`OSError`); `2` quando há
  `InvalidInput` ou erro de argumentos da CLI. Com `--out`, as pastas do caminho
  são criadas e o arquivo é escrito em UTF-8, sobrescrevendo o anterior. Sem
  `--out`, o JSON vai para o stdout e os logs para o stderr.
- **Motivação:** permitir que um script separe sucesso, erro de coleta e erro
  de uso só pelo código de saída, sem envelope no JSON.
- **Implementada em:** `collect_and_save` em `cli.py`.
- **Exceções:** um erro Python não tratado (por exemplo, configuração `KWAI_`
  inválida ou mudança de formato da API) também sai com `1`, mas com traceback.
  Exit `0` não prova completude do conteúdo da plataforma.
- **Verificação:** `tests/test_cli.py`.

## Relacionados

[Paginação](../flows/pagination.md) · [Ciclo de vida](../flows/runtime.md) ·
[CLI](../guides/cli.md#falhas-e-códigos-de-saída) ·
[Manutenção](../maintenance/maintenance.md).

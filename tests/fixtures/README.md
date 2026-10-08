# Capturas móveis para regressão

`mobile_comments.json`, `mobile_replies.json` e `mobile_profile.json` são
recortes de respostas capturadas em 07/10/2026 no Kwai Lite 10.3.20.539600,
antes do mapeamento para o contrato de saída. Conservam campos consumidos pelo
coletor e cursores originais; não contêm requisições, tokens ou dados de dispositivo.

As listas foram reduzidas: dois itens por página de comentários e perfil,
três respostas. Os cursores não indicam que esses recortes sejam páginas completas.
O teste de comentários usa um limite para não solicitar páginas ausentes.
Textos e identificadores públicos preservam a evidência do mapeamento; URLs de
mídia, metadados de rastreamento e previews de respostas foram omitidos.

O total declarado de respostas não deve ser igualado ao tamanho desta amostra.
Nenhum teste depende de emulador, Frida ou acesso à rede.

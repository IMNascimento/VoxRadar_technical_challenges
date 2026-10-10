# Fixtures de teste

Respostas reais do Kwai, recortadas para os testes offline.

| Arquivo | Origem | Usado em |
|---|---|---|
| `search_response.json` | Resposta da busca web (`/rest/o/w/pwa/v2/search/word/outer`), com três feeds. | `test_parser.py`, `test_cli.py` |
| `mobile_profile.json` | Página do feed de perfil móvel (`/rest/o/feed/profile`). | `test_cli.py` |
| `mobile_comments.json` | Duas páginas de comentários principais (`/rest/o/comment/list/v2`). | `test_parser.py`, `test_cli.py` |
| `mobile_replies.json` | Uma página de respostas (`/rest/o/comment/sublist`). | `test_cli.py` |

Os arquivos `mobile_*` vêm de respostas capturadas em 07/10/2026 no Kwai Lite
`10.3.20.539600`, antes da conversão para o formato de saída. Eles mantêm os
campos que o coletor usa e os cursores originais, mas não contêm requisições,
tokens nem dados de dispositivo. URLs de mídia, metadados de rastreamento e
prévias de respostas foram removidos.

As listas foram reduzidas: dois itens por página de comentários e de perfil e
três respostas. Os cursores não indicam que esses recortes sejam páginas
completas, e o total de respostas declarado (`sub_comment_count`) não deve ser
igualado ao tamanho da amostra.

`search_response.json` contém emojis com o caractere de junção (ZWJ,
U+200D) no texto dos posts. Isso é conteúdo real da busca, não um problema de
codificação.

Nenhum teste depende de emulador, Frida ou acesso à rede.

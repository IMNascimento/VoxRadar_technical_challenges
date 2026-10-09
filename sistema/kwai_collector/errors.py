"""Excecoes do kwai_collector."""


class CollectorError(Exception):
    """Erro generico e esperado do coletor (rede, parsing, validacao)."""


class InvalidUrlError(CollectorError):
    """A URL fornecida nao parece ser uma URL valida do Kwai."""


class NetworkError(CollectorError):
    """Falha de rede (timeout, DNS, conexao recusada, etc.)."""


class Sig3ServiceUnavailableError(CollectorError):
    """O servico local de assinatura __NS_sig3 (unidbg) nao esta no ar."""


class EmptyResultError(CollectorError):
    """A requisicao teve sucesso mas nao havia conteudo (ex.: pagina sem
    resultados, video sem comentarios). Nao e necessariamente um erro do
    usuario, mas e util distinguir de uma falha de rede/parsing."""

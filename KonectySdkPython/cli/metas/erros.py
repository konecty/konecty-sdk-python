"""Erros do `konecty-cli metas`."""

from __future__ import annotations


class MetasInvalidasError(Exception):
    """A árvore de metas, o delta ou o artefato não monta. A mensagem nomeia o arquivo de origem."""


class AplicacaoRecusadaError(Exception):
    """O artefato não pode ir para este tenant (sha256 ou ambiente). Nada foi enviado ao Konecty."""


class LoteRecusadoError(Exception):
    """O Konecty recusou o lote ou não respondeu depois das tentativas. O lote é transacional:
    nada foi gravado."""

"""Erros do `konecty-cli metas`."""

from __future__ import annotations


class MetasInvalidasError(Exception):
    """A árvore de metas, o delta ou o artefato não monta. A mensagem nomeia o arquivo de origem."""

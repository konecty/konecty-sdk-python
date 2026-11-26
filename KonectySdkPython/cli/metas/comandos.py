"""Comandos `konecty-cli metas ...`."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import click

from .erros import MetasInvalidasError
from .montar import BASE_REPO_PADRAO, montar


@click.group(name="metas")
def metas_group() -> None:
    """Metadado de base + delta por cliente: montar, gerar-delta, linter, diff, aplicar, deriva."""


@metas_group.command(name="montar")
@click.argument("repo", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--ambiente", required=True, type=click.Choice(["dev", "prod"]), help="Lê env/<ambiente>.env")
@click.option("--saida", required=True, type=click.Path(file_okay=False, path_type=Path), help="Pasta do artefato")
@click.option("--versao", default=None, help="Versão do cliente no manifesto (padrão: 'versao' do metadados.yaml)")
@click.option(
    "--base-dir",
    default=None,
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="metadata/base já extraída (pula o download da tag)",
)
@click.option("--base-repo", default=BASE_REPO_PADRAO, show_default=True, help="Repositório Git com as tags base-metas/*")
@click.option("--tar", "gerar_tar", is_flag=True, help="Também gera <cliente>-<versão>-<ambiente>.tar.gz")
def montar_command(
    repo: Path,
    ambiente: str,
    saida: Path,
    versao: Optional[str],
    base_dir: Optional[Path],
    base_repo: str,
    gerar_tar: bool,
) -> None:
    """Monta o artefato (itens.json, namespace.json, manifesto.json) de REPO."""
    try:
        manifesto = montar(
            repo, ambiente, saida, versao=versao, base_dir=base_dir, base_repo=base_repo, tar=gerar_tar
        )
    except MetasInvalidasError as erro:
        raise click.ClickException(str(erro)) from None
    click.echo(
        f"artefato {manifesto['cliente']} {manifesto['versaoCliente']} ({ambiente}) em {saida}: "
        f"{len(manifesto['documentos'])} documentos, delta {manifesto['deltaBytes']} bytes "
        f"({manifesto['deltaPct']}%), sha256 {manifesto['sha256Total']}"
    )

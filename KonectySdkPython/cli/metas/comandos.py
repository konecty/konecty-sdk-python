"""Comandos `konecty-cli metas ...`."""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

import click

from ...lib.client import KonectyClient

from .aplicar import aplicar
from .deriva import deriva
from .diff import diff
from .erros import AplicacaoRecusadaError, LoteRecusadoError, MetasInvalidasError
from .gerar_delta import gerar_delta
from .linter import linter
from .montar import BASE_REPO_PADRAO, montar, obter_base
from .repositorio import ler_config


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


@metas_group.command(name="gerar-delta")
@click.argument("base_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.argument("copia", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--saida", required=True, type=click.Path(file_okay=False, path_type=Path), help="Repositório do cliente")
@click.option("--cliente", required=True, help="Nome do cliente no metadados.yaml")
@click.option("--base", "base_tag", required=True, help="Tag da base em uso (base-metas/vX.Y.Z)")
@click.option("--konecty", default=None, help="Versão mínima do Konecty (ex.: '>=3.19.0')")
def gerar_delta_command(
    base_dir: Path, copia: Path, saida: Path, cliente: str, base_tag: str, konecty: Optional[str]
) -> None:
    """Migra a cópia completa COPIA para delta sobre BASE_DIR (metadata/base daquela tag)."""
    try:
        resumo = gerar_delta(base_dir, copia, saida, cliente=cliente, base_tag=base_tag, konecty=konecty)
    except MetasInvalidasError as erro:
        raise click.ClickException(str(erro)) from None
    click.echo(
        f"delta em {saida}: {len(resumo.patches)} patches, {len(resumo.novos)} metas novos, "
        f"{len(resumo.hooks)} hooks, {len(resumo.modulos)} módulos só do cliente, "
        f"{len(resumo.removidos)} removidos, {resumo.iguais} iguais à base"
    )


@metas_group.command(name="linter")
@click.argument("repo", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option(
    "--base-dir",
    default=None,
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="metadata/base já extraída (pula o download da tag)",
)
@click.option("--base-repo", default=BASE_REPO_PADRAO, show_default=True, help="Repositório Git com as tags base-metas/*")
def linter_command(repo: Path, base_dir: Optional[Path], base_repo: str) -> None:
    """Acusa delta redundante e conflito com a base. Sai com 1 se houver erro."""
    try:
        with tempfile.TemporaryDirectory(prefix="metas-base-") as temporario:
            raiz = base_dir or obter_base(ler_config(repo).base, base_repo, Path(temporario))
            achados = linter(repo, raiz)
    except MetasInvalidasError as erro:
        raise click.ClickException(str(erro)) from None
    for achado in achados:
        click.echo(str(achado))
    erros = sum(1 for achado in achados if achado.nivel == "erro")
    avisos = len(achados) - erros
    click.echo(f"linter: {erros} erros, {avisos} avisos")
    if erros:
        raise SystemExit(1)


@metas_group.command(name="diff")
@click.argument("artefato_a", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.argument("artefato_b", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--markdown", is_flag=True, help="Saída em Markdown, para comentário de PR")
def diff_command(artefato_a: Path, artefato_b: Path, markdown: bool) -> None:
    """Diff de ARTEFATO_A para ARTEFATO_B, por documento e por chave."""
    try:
        click.echo(diff(artefato_a, artefato_b, markdown=markdown), nl=False)
    except MetasInvalidasError as erro:
        raise click.ClickException(str(erro)) from None


def _client_do_ambiente(url: Optional[str]) -> KonectyClient:
    url = url or os.environ.get("KONECTY_URL")
    token = os.environ.get("KONECTY_TOKEN")
    if not url:
        raise click.ClickException("informe --url ou KONECTY_URL")
    if not token:
        raise click.ClickException("KONECTY_TOKEN não definido")
    return KonectyClient(base_url=url, token=token)


def _configurar_log() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


@metas_group.command(name="aplicar")
@click.argument("pasta", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--url", default=None, help="URL do Konecty (padrão: KONECTY_URL)")
def aplicar_command(pasta: Path, url: Optional[str]) -> None:
    """Aplica o artefato de PASTA no tenant (token em KONECTY_TOKEN, ambiente em TENANT_ENV).

    Sai com 2 quando o sha256 ou o ambiente não conferem (nada é enviado) e com 1 quando o
    Konecty recusa o lote ou não responde depois das tentativas.
    """
    _configurar_log()
    client = _client_do_ambiente(url)
    try:
        resultado = asyncio.run(
            aplicar(pasta, client, tenant_env=os.environ.get("TENANT_ENV"), origem=os.environ.get("GIT_COMMIT"))
        )
    except AplicacaoRecusadaError as erro:
        click.echo(f"Erro: {erro}", err=True)
        raise SystemExit(2) from None
    except (LoteRecusadoError, MetasInvalidasError) as erro:
        raise click.ClickException(str(erro)) from None
    click.echo(
        f"aplicados={resultado.aplicados} criados={len(resultado.criados)} "
        f"alterados={len(resultado.atualizados)} metadataVersion={'gravado' if resultado.versao_gravada else 'inalterado'}"
    )


@metas_group.command(name="deriva")
@click.argument("pasta", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--url", default=None, help="URL do Konecty (padrão: KONECTY_URL)")
@click.option("--tenant", default=None, help="Rótulo tenant da métrica (padrão: <cliente>-<ambiente>)")
def deriva_command(pasta: Path, url: Optional[str], tenant: Optional[str]) -> None:
    """Mede a divergência entre o tenant e o artefato de PASTA, só com dryRun (nunca escreve)."""
    _configurar_log()
    client = _client_do_ambiente(url)
    try:
        resultado = asyncio.run(deriva(pasta, client, tenant_env=os.environ.get("TENANT_ENV"), tenant=tenant))
    except AplicacaoRecusadaError as erro:
        click.echo(f"Erro: {erro}", err=True)
        raise SystemExit(2) from None
    except (LoteRecusadoError, MetasInvalidasError) as erro:
        raise click.ClickException(str(erro)) from None
    for linha in resultado.linhas():
        click.echo(linha)

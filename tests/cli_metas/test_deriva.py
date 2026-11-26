"""T19: `metas deriva` (MBD-14): só `dryRun`, métrica e lista por documento e chave."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

import pytest
from apoio_metas import TOKEN, KonectyFalso
from click.testing import CliRunner

from KonectySdkPython.cli import cli
from KonectySdkPython.cli.metas.deriva import deriva
from KonectySdkPython.cli.metas.erros import AplicacaoRecusadaError
from KonectySdkPython.cli.metas.montar import montar
from KonectySdkPython.lib.client import KonectyClient


@pytest.fixture
def artefato(repo_cliente: Path, base_dir: Path, tmp_path: Path) -> Path:
    montar(repo_cliente, "dev", tmp_path / "dist", base_dir=base_dir, versao="v1.0.0")
    return tmp_path / "dist"


async def nunca_dorme(_: float) -> None:
    return None


def itens(pasta: Path) -> dict:
    return {i["_id"]: i for i in json.loads((pasta / "itens.json").read_text("utf-8"))}


def tenant_derivado(konecty: KonectyFalso, artefato: Path) -> None:
    konecty.metas = dict(itens(artefato))
    konecty.metas["Product"] = {**konecty.metas["Product"], "name": "Mudado pela UI", "extra": 1}
    konecty.metas["Opportunity"] = {**konecty.metas["Opportunity"], "scriptAfterSave": "/* só no tenant */"}
    del konecty.metas["Product:access:Corretor"]


@pytest.mark.asyncio
async def test_nenhuma_chamada_sem_dry_run(konecty: KonectyFalso, artefato: Path) -> None:
    tenant_derivado(konecty, artefato)
    konecty.falhas = [503]
    await deriva(artefato, KonectyClient(base_url=konecty.base_url, token=TOKEN), tenant_env="dev", dormir=nunca_dorme)
    posts = [r for r in konecty.requisicoes if r["method"] != "GET"]
    assert posts and all(r["json"]["dryRun"] is True for r in posts)
    assert konecty.escritas == []
    assert "metadataVersion" not in konecty.namespace


@pytest.mark.asyncio
async def test_saida_traz_a_metrica_e_a_lista(
    konecty: KonectyFalso, artefato: Path, caplog: pytest.LogCaptureFixture
) -> None:
    tenant_derivado(konecty, artefato)
    with caplog.at_level(logging.INFO):
        resultado = await deriva(
            artefato, KonectyClient(base_url=konecty.base_url, token=TOKEN), tenant_env="dev", dormir=nunca_dorme
        )
    assert resultado.documentos == 3
    assert resultado.ausentes == ["Product:access:Corretor"]
    assert resultado.divergentes == {"Opportunity": ["scriptAfterSave"], "Product": ["extra", "name"]}
    assert 'konecty_metadata_drift_documents{tenant="acme-dev"} 3' in caplog.text
    assert "diverge: Product: extra, name" in caplog.text
    assert "ausente no tenant: Product:access:Corretor" in caplog.text
    assert TOKEN not in caplog.text


@pytest.mark.asyncio
async def test_sem_deriva_a_metrica_e_zero(konecty: KonectyFalso, artefato: Path) -> None:
    konecty.metas = dict(itens(artefato))
    resultado = await deriva(
        artefato, KonectyClient(base_url=konecty.base_url, token=TOKEN), tenant_env="dev", tenant="aux-dev", dormir=nunca_dorme
    )
    assert resultado.linhas() == ['konecty_metadata_drift_documents{tenant="aux-dev"} 0']


@pytest.mark.asyncio
async def test_ambiente_trocado_recusa_sem_chamar_a_api(konecty: KonectyFalso, artefato: Path) -> None:
    with pytest.raises(AplicacaoRecusadaError):
        await deriva(artefato, KonectyClient(base_url=konecty.base_url, token=TOKEN), tenant_env="prod", dormir=nunca_dorme)
    assert konecty.requisicoes == []


@pytest.mark.asyncio
async def test_cli_deriva_imprime_a_metrica(konecty: KonectyFalso, artefato: Path) -> None:
    tenant_derivado(konecty, artefato)
    # O CLI roda o próprio event loop: em outra thread, para o servidor falso seguir atendendo.
    resultado = await asyncio.to_thread(
        CliRunner().invoke,
        cli,
        ["metas", "deriva", str(artefato), "--url", konecty.base_url],
        env={"KONECTY_TOKEN": TOKEN, "TENANT_ENV": "dev"},
    )
    assert resultado.exit_code == 0, resultado.output
    assert 'konecty_metadata_drift_documents{tenant="acme-dev"} 3' in resultado.output
    assert TOKEN not in resultado.output
    assert konecty.escritas == []

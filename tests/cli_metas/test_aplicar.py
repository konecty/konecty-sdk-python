"""T18: `metas aplicar` (MBD-06, 08, 09) contra um Konecty falso por HTTP.

O falso imita o contrato de `POST /api/document` (`src/server/routes/api/document/index.ts` e
`src/imports/meta/applyBulk.ts` no Konecty): `dryRun` devolve `plan` sem gravar; sem `dryRun`
grava os itens por replace e aplica `namespacePatch` como `$set` de topo.
"""

from __future__ import annotations

import json
import logging
import socket
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest
import pytest_asyncio
from aiohttp import web
from apoio_metas import escrever
from click.testing import CliRunner

from KonectySdkPython.cli import cli
from KonectySdkPython.cli.metas.aplicar import aplicar
from KonectySdkPython.cli.metas.erros import AplicacaoRecusadaError, LoteRecusadoError
from KonectySdkPython.cli.metas.montar import montar
from KonectySdkPython.lib.client import KonectyClient

TOKEN = "fake-pat-metaapply-nao-e-real-0123456789"
HOOKS = ("scriptBeforeValidation", "validationScript", "scriptAfterSave", "validationData")


class KonectyFalso:
    def __init__(self) -> None:
        self.metas: Dict[str, Dict[str, Any]] = {}
        self.namespace: Dict[str, Any] = {"_id": "Namespace", "type": "namespace", "ns": "acme"}
        self.requisicoes: List[Dict[str, Any]] = []
        self.falhas: List[int] = []
        self.status_leitura_namespace = 200
        self.erros_de_schema: Optional[List[Dict[str, Any]]] = None
        self.preserved_hooks: Dict[str, List[str]] = {}
        self.app = web.Application()
        self.app.router.add_route("*", "/{tail:.*}", self._atender)
        self.base_url = ""

    @property
    def escritas(self) -> List[Dict[str, Any]]:
        return [r["json"] for r in self.requisicoes if r["path"] == "/api/document" and not r["json"].get("dryRun")]

    @property
    def simulacoes(self) -> List[Dict[str, Any]]:
        return [r["json"] for r in self.requisicoes if r["path"] == "/api/document" and r["json"].get("dryRun")]

    async def _atender(self, request: web.Request) -> web.Response:
        corpo = await request.json() if request.can_read_body else None
        self.requisicoes.append(
            {"method": request.method, "path": request.path, "json": corpo, "authorization": request.headers.get("Authorization")}
        )
        if request.path == "/rest/auth/info":
            return web.json_response({"logged": True, "user": {"_id": "sa-metas"}})
        if request.path == "/api/admin/meta/Namespace":
            if self.status_leitura_namespace != 200:
                return web.Response(text="Unauthorized", status=self.status_leitura_namespace)
            return web.json_response({"success": True, "data": [self.namespace]})
        if request.path != "/api/document" or request.method != "POST":
            return web.Response(status=404)
        if self.falhas:
            status = self.falhas.pop(0)
            return web.Response(text="Internal server error", status=status)
        itens = corpo.get("items") or []
        if not itens:
            return web.json_response({"error": "items must not be empty"}, status=400)
        if self.erros_de_schema is not None:
            return web.json_response({"errors": self.erros_de_schema}, status=400)
        if corpo.get("dryRun"):
            return web.json_response(self._plano(itens, corpo.get("hookMode")))
        for item in itens:
            self.metas[item["_id"]] = item
        if corpo.get("namespacePatch"):
            self.namespace.update(corpo["namespacePatch"])
        return web.json_response(
            {"applied": len(itens), "created": 0, "updated": 0, "deleted": 0, "warnings": [], "preservedHooks": self.preserved_hooks}
        )

    def _plano(self, itens: List[Dict[str, Any]], hook_mode: Optional[str]) -> Dict[str, Any]:
        plano: Dict[str, Any] = {"created": [], "updated": [], "unchanged": 0, "hooksRemoved": {}}
        for item in itens:
            atual = self.metas.get(item["_id"])
            if atual is None:
                plano["created"].append(item["_id"])
                continue
            chaves = sorted(k for k in set(item) | set(atual) if item.get(k) != atual.get(k))
            if chaves:
                plano["updated"].append({"_id": item["_id"], "keys": chaves})
            else:
                plano["unchanged"] += 1
            removidos = [h for h in HOOKS if atual.get(h) is not None and item.get(h) is None]
            if removidos and hook_mode == "replace":
                plano["hooksRemoved"][item["_id"]] = removidos
        return {"applied": 0, "created": 0, "updated": 0, "deleted": 0, "warnings": [], "preservedHooks": {}, "plan": plano}


@pytest_asyncio.fixture
async def konecty():
    falso = KonectyFalso()
    runner = web.AppRunner(falso.app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    falso.base_url = f"http://127.0.0.1:{runner.addresses[0][1]}"
    try:
        yield falso
    finally:
        await runner.cleanup()


@pytest.fixture
def artefato(repo_cliente: Path, base_dir: Path, tmp_path: Path) -> Path:
    montar(repo_cliente, "dev", tmp_path / "dist", base_dir=base_dir, versao="v1.0.0")
    return tmp_path / "dist"


class Relogio:
    def __init__(self) -> None:
        self.esperas: List[float] = []

    async def __call__(self, segundos: float) -> None:
        self.esperas.append(segundos)


def client(konecty: KonectyFalso) -> KonectyClient:
    return KonectyClient(base_url=konecty.base_url, token=TOKEN)


def itens(pasta: Path) -> Dict[str, Dict[str, Any]]:
    return {i["_id"]: i for i in json.loads((pasta / "itens.json").read_text("utf-8"))}


# ------------------------------------------------------------------ AC 1, 2, 4


@pytest.mark.asyncio
async def test_aplica_so_o_que_difere_depois_do_dry_run(konecty: KonectyFalso, artefato: Path) -> None:
    konecty.metas = dict(itens(artefato))
    konecty.metas["Product"] = {**konecty.metas["Product"], "name": "Antigo"}
    del konecty.metas["Opportunity:view:Default"]

    resultado = await aplicar(artefato, client(konecty), tenant_env="dev", dormir=Relogio())

    simulacao, escrita = konecty.simulacoes[0], konecty.escritas[0]
    assert simulacao["hookMode"] == "replace"
    assert len(simulacao["items"]) == len(itens(artefato))
    assert [i["_id"] for i in escrita["items"]] == ["Opportunity:view:Default", "Product"]
    assert escrita["hookMode"] == "replace"
    assert escrita.get("deleteRemoved", False) is False
    assert "dryRun" not in escrita
    assert resultado.aplicados == 2
    assert konecty.metas["Product"] == itens(artefato)["Product"]
    assert all(r["authorization"] == TOKEN for r in konecty.requisicoes)


@pytest.mark.asyncio
async def test_grava_metadata_version_e_o_namespace_do_artefato(konecty: KonectyFalso, artefato: Path) -> None:
    from datetime import datetime, timezone

    momento = datetime(2026, 11, 26, 12, 0, tzinfo=timezone.utc)
    await aplicar(
        artefato, client(konecty), tenant_env="dev", origem="abc123", dormir=Relogio(), agora=lambda: momento
    )
    manifesto = json.loads((artefato / "manifesto.json").read_text("utf-8"))
    patch = konecty.escritas[0]["namespacePatch"]
    assert patch["metadataVersion"] == {
        "cliente": "acme",
        "versaoCliente": "v1.0.0",
        "base": "base-metas/v1.0.0",
        "sha256": manifesto["sha256Total"],
        "ambiente": "dev",
        "aplicadoEm": "2026-11-26T12:00:00Z",
        "aplicadoPor": "sa-metas",
        "origem": "abc123",
    }
    namespace = json.loads((artefato / "namespace.json").read_text("utf-8"))
    assert {k: v for k, v in patch.items() if k != "metadataVersion"} == namespace
    assert not {"_id", "type", "ns"} & set(patch)


# ------------------------------------------------------------------ AC 5 e concorrência


@pytest.mark.asyncio
async def test_mesmo_artefato_de_novo_da_aplicados_0_sem_escrever(konecty: KonectyFalso, artefato: Path) -> None:
    primeira = await aplicar(artefato, client(konecty), tenant_env="dev", dormir=Relogio())
    assert primeira.aplicados == len(itens(artefato))
    escritas_antes = len(konecty.escritas)

    segunda = await aplicar(artefato, client(konecty), tenant_env="dev", dormir=Relogio())

    assert segunda.aplicados == 0
    assert segunda.versao_gravada is False
    assert len(konecty.escritas) == escritas_antes


@pytest.mark.asyncio
async def test_segundo_disparo_da_mesma_versao_encontra_aplicados_0(konecty: KonectyFalso, artefato: Path) -> None:
    """Dois Jobs `aplicar-metas-<versão>`: o que chega depois só simula e sai com 0."""
    await aplicar(artefato, client(konecty), tenant_env="dev", dormir=Relogio())
    segundo = await aplicar(artefato, KonectyClient(base_url=konecty.base_url, token=TOKEN), tenant_env="dev", dormir=Relogio())
    assert segundo.aplicados == 0
    assert len(konecty.escritas) == 1


@pytest.mark.asyncio
async def test_plano_vazio_com_versao_ausente_grava_so_a_versao(konecty: KonectyFalso, artefato: Path) -> None:
    konecty.metas = dict(itens(artefato))
    resultado = await aplicar(artefato, client(konecty), tenant_env="dev", dormir=Relogio())
    assert resultado.aplicados == 0
    assert resultado.versao_gravada is True
    assert len(konecty.escritas[0]["items"]) == 1
    assert "metadataVersion" in konecty.namespace


@pytest.mark.asyncio
async def test_plano_vazio_com_versao_ilegivel_nao_escreve(
    konecty: KonectyFalso, artefato: Path, caplog: pytest.LogCaptureFixture
) -> None:
    konecty.metas = dict(itens(artefato))
    konecty.status_leitura_namespace = 403
    with caplog.at_level(logging.WARNING):
        resultado = await aplicar(artefato, client(konecty), tenant_env="dev", dormir=Relogio())
    assert resultado.aplicados == 0
    assert konecty.escritas == []
    assert "ilegível" in caplog.text


# ------------------------------------------------------------------ AC 3: 400


@pytest.mark.asyncio
async def test_400_falha_com_a_lista_completa_mapeada_para_o_arquivo(
    konecty: KonectyFalso, repo_cliente: Path, base_dir: Path, tmp_path: Path
) -> None:
    escrever(repo_cliente, "delta/Product/document.json", {"icon": "home"})
    montar(repo_cliente, "dev", tmp_path / "dist", base_dir=base_dir)
    ids = sorted(itens(tmp_path / "dist"))
    konecty.erros_de_schema = [
        {"index": ids.index("Product"), "path": "fields.status.type", "message": "Invalid enum value"},
        {"message": "Required", "details": f"index {ids.index('Opportunity')}, path: name"},
    ]
    with pytest.raises(LoteRecusadoError) as erro:
        await aplicar(tmp_path / "dist", client(konecty), tenant_env="dev", dormir=Relogio())
    mensagem = str(erro.value)
    assert "Product (base:Product/document.json + delta/Product/document.json): fields.status.type Invalid enum value" in mensagem
    assert "Opportunity (base:Opportunity/document.json): name Required" in mensagem
    assert konecty.escritas == []
    assert konecty.metas == {}


# ------------------------------------------------------------------ AC 6


@pytest.mark.asyncio
async def test_preserved_hooks_e_hooks_removidos_vao_ao_log(
    konecty: KonectyFalso, artefato: Path, caplog: pytest.LogCaptureFixture
) -> None:
    konecty.metas = {"Opportunity": {**itens(artefato)["Opportunity"], "scriptAfterSave": "/* só no servidor */"}}
    konecty.preserved_hooks = {"Opportunity": ["scriptAfterSave"]}
    with caplog.at_level(logging.INFO):
        resultado = await aplicar(artefato, client(konecty), tenant_env="dev", dormir=Relogio())
    assert resultado.hooks_removidos == {"Opportunity": ["scriptAfterSave"]}
    assert resultado.preserved_hooks == {"Opportunity": ["scriptAfterSave"]}
    assert "scriptAfterSave" in caplog.text


# ------------------------------------------------------------------ AC 7 e ambiente


@pytest.mark.asyncio
async def test_sha256_que_nao_confere_falha_antes_da_api(konecty: KonectyFalso, artefato: Path) -> None:
    conteudo = (artefato / "itens.json").read_text("utf-8").replace('"Product"', '"Produto"', 1)
    (artefato / "itens.json").write_text(conteudo, encoding="utf-8")
    with pytest.raises(AplicacaoRecusadaError, match="sha256"):
        await aplicar(artefato, client(konecty), tenant_env="dev", dormir=Relogio())
    assert konecty.requisicoes == []


@pytest.mark.asyncio
async def test_ambiente_trocado_e_recusado_antes_da_api(konecty: KonectyFalso, artefato: Path) -> None:
    with pytest.raises(AplicacaoRecusadaError, match="'dev'.*'prod'"):
        await aplicar(artefato, client(konecty), tenant_env="prod", dormir=Relogio())
    with pytest.raises(AplicacaoRecusadaError, match="TENANT_ENV"):
        await aplicar(artefato, client(konecty), tenant_env=None, dormir=Relogio())
    assert konecty.requisicoes == []


# ------------------------------------------------------------------ retry


@pytest.mark.asyncio
async def test_5xx_tenta_de_novo_com_5_15_e_45_segundos(konecty: KonectyFalso, artefato: Path) -> None:
    konecty.falhas = [502, 503]
    relogio = Relogio()
    resultado = await aplicar(artefato, client(konecty), tenant_env="dev", dormir=relogio)
    assert relogio.esperas == [5.0, 15.0]
    assert resultado.aplicados == len(itens(artefato))


@pytest.mark.asyncio
async def test_retry_esgotado_falha_sem_gravar(konecty: KonectyFalso, artefato: Path) -> None:
    konecty.falhas = [500, 500, 500, 500]
    relogio = Relogio()
    with pytest.raises(LoteRecusadoError, match="4 tentativas"):
        await aplicar(artefato, client(konecty), tenant_env="dev", dormir=relogio)
    assert relogio.esperas == [5.0, 15.0, 45.0]
    assert len(konecty.simulacoes) == 4 and konecty.escritas == []


@pytest.mark.asyncio
async def test_falha_de_rede_tambem_tenta_de_novo(artefato: Path) -> None:
    with socket.socket() as livre:
        livre.bind(("127.0.0.1", 0))
        porta = livre.getsockname()[1]
    relogio = Relogio()
    with pytest.raises(LoteRecusadoError, match="sem resposta"):
        await aplicar(
            artefato, KonectyClient(base_url=f"http://127.0.0.1:{porta}", token=TOKEN), tenant_env="dev", dormir=relogio
        )
    assert relogio.esperas == [5.0, 15.0, 45.0]


@pytest.mark.asyncio
async def test_400_nao_tenta_de_novo(konecty: KonectyFalso, artefato: Path) -> None:
    konecty.erros_de_schema = [{"index": 0, "path": "x", "message": "bad"}]
    relogio = Relogio()
    with pytest.raises(LoteRecusadoError):
        await aplicar(artefato, client(konecty), tenant_env="dev", dormir=relogio)
    assert relogio.esperas == []
    assert len(konecty.simulacoes) == 1


# ------------------------------------------------------------------ token fora do log


@pytest.mark.asyncio
async def test_token_nunca_aparece_no_log_nem_no_erro(
    konecty: KonectyFalso, artefato: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG):
        konecty.falhas = [503]
        await aplicar(artefato, client(konecty), tenant_env="dev", dormir=Relogio())
        konecty.status_leitura_namespace = 401
        konecty.erros_de_schema = [{"index": 0, "path": "x", "message": "bad"}]
        with pytest.raises(LoteRecusadoError) as erro:
            await aplicar(artefato, client(konecty), tenant_env="dev", dormir=Relogio())
    assert caplog.records
    assert TOKEN not in caplog.text
    assert TOKEN not in str(erro.value)


# ------------------------------------------------------------------ CLI


def test_cli_ambiente_trocado_sai_com_2_e_sem_token_na_saida(artefato: Path) -> None:
    resultado = CliRunner().invoke(
        cli,
        ["metas", "aplicar", str(artefato), "--url", "http://127.0.0.1:9"],
        env={"KONECTY_TOKEN": TOKEN, "TENANT_ENV": "prod"},
    )
    assert resultado.exit_code == 2
    assert "ambiente" in resultado.output
    assert TOKEN not in resultado.output


def test_cli_sem_token_falha(artefato: Path) -> None:
    resultado = CliRunner().invoke(
        cli, ["metas", "aplicar", str(artefato), "--url", "http://127.0.0.1:9"], env={"KONECTY_TOKEN": "", "TENANT_ENV": "dev"}
    )
    assert resultado.exit_code == 1
    assert "KONECTY_TOKEN" in resultado.output

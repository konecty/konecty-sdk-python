"""T15: `metas gerar-delta` (MBD-10): `montar(gerar-delta(base, cópia)) == ler_arvore(cópia)`."""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

import pytest
import yaml
from apoio_metas import PRODUCT, escrever
from click.testing import CliRunner

from KonectySdkPython.cli import cli
from KonectySdkPython.cli.metas.arvore import ler_arvore
from KonectySdkPython.cli.metas.erros import MetasInvalidasError
from KonectySdkPython.cli.metas.gerar_delta import gerar_delta
from KonectySdkPython.cli.metas.montar import montar


def montado(repo: Path, base_dir: Path, saida: Path) -> dict:
    # O Namespace da base tem placeholders; o env do ambiente entra à mão depois da migração.
    escrever(repo, "env/dev.env", "SITE_URL=https://dev.example.invalid\nSMTP_PASS=fake-dev\n")
    montar(repo, "dev", saida, base_dir=base_dir)
    return {item["_id"]: item for item in json.loads((saida / "itens.json").read_text("utf-8"))}


@pytest.fixture
def copia(base_dir: Path, tmp_path: Path) -> Path:
    """Cópia completa do cliente, derivada da base com todo tipo de diferença."""
    raiz = tmp_path / "copia"
    shutil.copytree(base_dir, raiz)
    (raiz / "Namespace.json").unlink()
    produto = copy.deepcopy(PRODUCT)
    produto["fields"]["status"]["options"]["Vendido"] = {"pt_BR": "Vendido"}
    del produto["fields"]["site"]
    produto["fields"]["code"]["label"] = None  # null legítimo (E3)
    produto["fields"]["tags"] = {"type": "text", "default": None}
    escrever(raiz, "Product/document.json", produto)
    escrever(raiz, "Product/hook/scriptBeforeValidation.js", "/* do cliente */\n")
    escrever(raiz, "Product/hook/validationData.json", {"user": {"document": "User", "fields": "_id,name"}})
    escrever(raiz, "Product/hook/scriptAfterSave.js", "/* hook novo */\n")
    (raiz / "Product/access/Corretor.json").unlink()
    escrever(
        raiz,
        "Product/access/Gerente Gestão de Imóveis.json",
        {"_id": "Product:access:Gerente Gestão de Imóveis", "type": "access", "fieldDefaults": {"isReadable": False}},
    )
    escrever(raiz, "Opportunity/view/Default.json", {"_id": "Opportunity:view:Default", "type": "view", "url": "https://x.example.invalid/op"})
    escrever(raiz, "Imovel360/document.json", {"_id": "Imovel360", "type": "document", "fields": {"a": {"type": "text"}}})
    escrever(raiz, "Imovel360/hook/validationScript.js", "/* só cliente */\n")
    escrever(raiz, "Imovel360/list/Default.json", {"_id": "Imovel360:list:Default", "type": "list"})
    return raiz


def test_ida_e_volta_documento_a_documento(base_dir: Path, copia: Path, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    gerar_delta(base_dir, copia, repo, cliente="acme", base_tag="base-metas/v1.0.0")
    esperado = ler_arvore(copia, placeholders="manter")
    itens = montado(repo, base_dir, tmp_path / "dist")
    assert set(itens) == set(esperado)
    for meta_id, meta in esperado.items():
        assert itens[meta_id] == meta, meta_id


def test_hook_que_a_base_tem_e_a_copia_nao_sai_na_ida_e_volta(base_dir: Path, copia: Path, tmp_path: Path) -> None:
    (copia / "Product/hook/validationData.json").unlink()
    repo = tmp_path / "repo"
    gerar_delta(base_dir, copia, repo, cliente="acme", base_tag="base-metas/v1.0.0")
    assert json.loads((repo / "delta/Product/document.json").read_text("utf-8"))["validationData"] is None
    assert "validationData" not in montado(repo, base_dir, tmp_path / "dist")["Product"]


def test_estrutura_gerada(base_dir: Path, copia: Path, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    resumo = gerar_delta(base_dir, copia, repo, cliente="acme", base_tag="base-metas/v1.0.0", konecty=">=3.19.0")
    config = yaml.safe_load((repo / "metadados.yaml").read_text("utf-8"))
    assert config == {
        "cliente": "acme",
        "base": "base-metas/v1.0.0",
        "konecty": ">=3.19.0",
        "removidos": ["Product:access:Corretor"],
        "naoMigrados": [],
    }
    assert (repo / "modulos/Imovel360/document.json").is_file()
    assert (repo / "modulos/Imovel360/hook/validationScript.js").is_file()
    assert (repo / "delta/Product/hook/scriptAfterSave.js").read_text("utf-8") == "/* hook novo */\n"
    assert (repo / "delta/Product/access/Gerente Gestão de Imóveis.json").is_file()
    assert not (repo / "delta/Product/list/Default.json").exists()
    assert not (repo / "delta/Opportunity/document.json").exists()
    assert resumo.modulos == ["Imovel360"]
    assert resumo.removidos == ["Product:access:Corretor"]


def test_patch_so_traz_o_que_difere(base_dir: Path, copia: Path, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    gerar_delta(base_dir, copia, repo, cliente="acme", base_tag="base-metas/v1.0.0")
    patch = json.loads((repo / "delta/Product/document.json").read_text("utf-8"))
    assert patch == {
        "fields": {
            "code": {"label": {"$null": True}},
            "status": {"options": {"Vendido": {"pt_BR": "Vendido"}}},
            "site": None,
            "tags": {"type": "text", "default": {"$null": True}},
        }
    }


def test_copia_igual_a_base_gera_delta_vazio(base_dir: Path, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    resumo = gerar_delta(base_dir, base_dir, repo, cliente="acme", base_tag="base-metas/v1.0.0")
    assert resumo.patches == [] and resumo.novos == [] and resumo.removidos == []
    assert not (repo / "delta").exists()


def test_nao_sobrescreve_repositorio_existente(base_dir: Path, copia: Path, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    escrever(repo, "metadados.yaml", "cliente: x\n")
    with pytest.raises(MetasInvalidasError, match="não sobrescreve"):
        gerar_delta(base_dir, copia, repo, cliente="acme", base_tag="base-metas/v1.0.0")


def test_cli_gerar_delta(base_dir: Path, copia: Path, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    resultado = CliRunner().invoke(
        cli,
        ["metas", "gerar-delta", str(base_dir), str(copia), "--saida", str(repo), "--cliente", "acme", "--base", "base-metas/v1.0.0"],
    )
    assert resultado.exit_code == 0, resultado.output
    assert "1 removidos" in resultado.output
    assert (repo / "metadados.yaml").is_file()

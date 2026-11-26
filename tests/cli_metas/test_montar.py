"""T14: `metas montar` (MBD-01, MBD-02; emendas E1, E2, E5)."""

from __future__ import annotations

import hashlib
import json
import logging
import tarfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from KonectySdkPython.cli import cli
from KonectySdkPython.cli.metas.artefato import ler_artefato
from KonectySdkPython.cli.metas.erros import MetasInvalidasError
from KonectySdkPython.cli.metas.montar import montar

from apoio_metas import PRODUCT, PRODUCT_SCRIPT, config_yaml, escrever


def itens_por_id(saida: Path) -> dict:
    return {item["_id"]: item for item in json.loads((saida / "itens.json").read_text("utf-8"))}


# ---------------------------------------------------------------- MBD-01.1: ordem da montagem


def test_sem_delta_o_artefato_e_a_base_com_hooks(repo_cliente: Path, base_dir: Path, tmp_path: Path) -> None:
    saida = tmp_path / "dist"
    montar(repo_cliente, "dev", saida, base_dir=base_dir)
    itens = itens_por_id(saida)
    assert set(itens) == {
        "Product",
        "Product:list:Default",
        "Product:access:Corretor",
        "Product:access:Default",
        "Opportunity",
        "Opportunity:view:Default",
    }
    assert itens["Product"]["scriptBeforeValidation"] == PRODUCT_SCRIPT
    assert itens["Product"]["validationData"] == {"user": {"document": "User", "fields": "_id"}}
    assert itens["Product"]["fields"] == PRODUCT["fields"]


def test_base_depois_delta_depois_modulos_depois_removidos(
    repo_cliente: Path, base_dir: Path, tmp_path: Path
) -> None:
    escrever(repo_cliente, "metadados.yaml", config_yaml(removidos=["Product:access:Corretor"]))
    escrever(
        repo_cliente,
        "delta/Product/document.json",
        {"fields": {"status": {"options": {"Vendido": {"pt_BR": "Vendido"}}}, "site": None}},
    )
    escrever(repo_cliente, "delta/Product/hook/scriptBeforeValidation.js", "/* cliente */\n")
    escrever(repo_cliente, "delta/Product/hook/validationData.json", {"office": {"document": "Office"}})
    escrever(repo_cliente, "delta/Product/access/Gerente.json", {"_id": "Product:access:Gerente", "type": "access"})
    escrever(repo_cliente, "modulos/Imovel360/document.json", {"_id": "Imovel360", "type": "document"})
    escrever(repo_cliente, "modulos/Imovel360/hook/scriptAfterSave.js", "/* só cliente */\n")
    saida = tmp_path / "dist"
    montar(repo_cliente, "dev", saida, base_dir=base_dir)
    itens = itens_por_id(saida)

    produto = itens["Product"]
    assert set(produto["fields"]["status"]["options"]) == {"Ativo", "Vendido"}
    assert "site" not in produto["fields"]
    assert produto["fields"]["code"] == PRODUCT["fields"]["code"]
    assert produto["scriptBeforeValidation"] == "/* cliente */\n"
    assert produto["validationData"] == {
        "user": {"document": "User", "fields": "_id"},
        "office": {"document": "Office"},
    }
    assert itens["Product:access:Gerente"] == {"_id": "Product:access:Gerente", "type": "access"}
    assert itens["Imovel360"]["scriptAfterSave"] == "/* só cliente */\n"
    assert "Product:access:Corretor" not in itens


def test_hook_da_base_sai_com_null_no_patch_do_document(
    repo_cliente: Path, base_dir: Path, tmp_path: Path
) -> None:
    escrever(repo_cliente, "delta/Product/document.json", {"scriptBeforeValidation": None})
    montar(repo_cliente, "dev", tmp_path / "dist", base_dir=base_dir)
    assert "scriptBeforeValidation" not in itens_por_id(tmp_path / "dist")["Product"]


def test_marcador_null_grava_null_literal(repo_cliente: Path, base_dir: Path, tmp_path: Path) -> None:
    escrever(repo_cliente, "delta/Product/document.json", {"fields": {"code": {"label": {"$null": True}}}})
    montar(repo_cliente, "dev", tmp_path / "dist", base_dir=base_dir)
    assert itens_por_id(tmp_path / "dist")["Product"]["fields"]["code"]["label"] is None


# ---------------------------------------------------------------- MBD-02: formato e manifesto


def test_artefato_tem_itens_namespace_e_manifesto(repo_cliente: Path, base_dir: Path, tmp_path: Path) -> None:
    escrever(repo_cliente, "delta/Product/document.json", {"fields": {"site": None}})
    saida = tmp_path / "dist"
    montar(repo_cliente, "prod", saida, base_dir=base_dir, versao="v1.4.0")
    artefato = ler_artefato(saida)
    manifesto = artefato.manifesto

    ids = [item["_id"] for item in artefato.itens]
    assert ids == sorted(ids)
    assert manifesto["cliente"] == "acme"
    assert manifesto["versaoCliente"] == "v1.4.0"
    assert manifesto["base"] == "base-metas/v1.0.0"
    assert manifesto["konectyMin"] == ">=3.19.0"
    assert manifesto["ambiente"] == "prod"
    assert manifesto["naoMigrados"] == []
    assert set(manifesto["documentos"]) == set(ids)
    for item in artefato.itens:
        canonico = json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        assert manifesto["documentos"][item["_id"]] == hashlib.sha256(canonico).hexdigest()
    total = hashlib.sha256((saida / "itens.json").read_bytes() + (saida / "namespace.json").read_bytes())
    assert manifesto["sha256Total"] == total.hexdigest()
    assert manifesto["origens"]["Product"] == ["base:Product/document.json", "delta/Product/document.json"]


def test_delta_bytes_e_pct_medem_o_delta_sobre_os_arquivos_comuns(
    repo_cliente: Path, base_dir: Path, tmp_path: Path
) -> None:
    patch = escrever(repo_cliente, "delta/Product/document.json", {"fields": {"site": None}})
    escrever(repo_cliente, "delta/Product/access/Novo.json", {"_id": "Product:access:Novo", "type": "access"})
    manifesto = montar(repo_cliente, "dev", tmp_path / "dist", base_dir=base_dir)
    comum = (base_dir / "Product/document.json").stat().st_size
    assert manifesto["deltaBytes"] == patch.stat().st_size
    assert manifesto["deltaPct"] == round(100 * patch.stat().st_size / comum, 1)


def test_namespace_vem_da_base_com_patch_e_sem_campos_imutaveis(
    repo_cliente: Path, base_dir: Path, tmp_path: Path
) -> None:
    escrever(repo_cliente, "delta/Namespace.json", {"emailServers": None, "mcpUserEnabled": True})
    montar(repo_cliente, "prod", tmp_path / "dist", base_dir=base_dir)
    namespace = json.loads((tmp_path / "dist/namespace.json").read_text("utf-8"))
    assert namespace == {"name": "konecty", "siteUrl": "https://example.invalid", "mcpUserEnabled": True}
    assert "metadataVersion" not in namespace


def test_placeholders_resolvidos_pelo_env_do_ambiente(repo_cliente: Path, base_dir: Path, tmp_path: Path) -> None:
    montar(repo_cliente, "dev", tmp_path / "dev", base_dir=base_dir)
    montar(repo_cliente, "prod", tmp_path / "prod", base_dir=base_dir)
    assert itens_por_id(tmp_path / "dev")["Opportunity:view:Default"]["url"] == "https://dev.example.invalid/op"
    assert itens_por_id(tmp_path / "prod")["Opportunity:view:Default"]["url"] == "https://example.invalid/op"
    assert "__" not in (tmp_path / "prod/itens.json").read_text("utf-8")


def test_modulo_nao_migrado_entra_como_copia_integral_e_vai_ao_manifesto(
    repo_cliente: Path, base_dir: Path, tmp_path: Path
) -> None:
    escrever(repo_cliente, "metadados.yaml", config_yaml(naoMigrados=["Opportunity"]))
    escrever(repo_cliente, "modulos/Opportunity/document.json", {"_id": "Opportunity", "type": "document", "name": "Op"})
    manifesto = montar(repo_cliente, "dev", tmp_path / "dist", base_dir=base_dir)
    itens = itens_por_id(tmp_path / "dist")
    assert itens["Opportunity"] == {"_id": "Opportunity", "type": "document", "name": "Op"}
    assert "Opportunity:view:Default" not in itens
    assert manifesto["naoMigrados"] == ["Opportunity"]


# ---------------------------------------------------------------- MBD-02.3: determinismo


def test_duas_montagens_dao_o_mesmo_sha256_e_os_mesmos_bytes(
    repo_cliente: Path, base_dir: Path, tmp_path: Path
) -> None:
    escrever(repo_cliente, "delta/Product/document.json", {"fields": {"site": None, "novo": {"type": "text"}}})
    escrever(repo_cliente, "modulos/Zeta/document.json", {"_id": "Zeta", "type": "document"})
    a = montar(repo_cliente, "dev", tmp_path / "a", base_dir=base_dir, versao="v1", tar=True)
    b = montar(repo_cliente, "dev", tmp_path / "b", base_dir=base_dir, versao="v1", tar=True)
    assert a["sha256Total"] == b["sha256Total"]
    for nome in ("itens.json", "namespace.json", "manifesto.json", "acme-v1-dev.tar.gz"):
        assert (tmp_path / "a" / nome).read_bytes() == (tmp_path / "b" / nome).read_bytes(), nome


def test_tar_gz_traz_os_tres_arquivos(repo_cliente: Path, base_dir: Path, tmp_path: Path) -> None:
    montar(repo_cliente, "dev", tmp_path / "dist", base_dir=base_dir, versao="v2", tar=True)
    with tarfile.open(tmp_path / "dist/acme-v2-dev.tar.gz") as tar:
        assert sorted(tar.getnames()) == ["metas/itens.json", "metas/manifesto.json", "metas/namespace.json"]


# ---------------------------------------------------------------- casos de borda


def test_delta_de_modulo_orfao_falha_nomeando_o_arquivo(repo_cliente: Path, base_dir: Path, tmp_path: Path) -> None:
    orfao = escrever(repo_cliente, "delta/Fantasma/document.json", {"fields": {}})
    with pytest.raises(MetasInvalidasError) as erro:
        montar(repo_cliente, "dev", tmp_path / "dist", base_dir=base_dir)
    assert str(orfao) in str(erro.value)
    assert not (tmp_path / "dist").exists()


def test_placeholder_sem_valor_falha_nomeando_o_token(repo_cliente: Path, base_dir: Path, tmp_path: Path) -> None:
    escrever(repo_cliente, "delta/Product/hook/scriptAfterSave.js", "send('__FEED_PUBLIC_BASE_URL__');\n")
    with pytest.raises(MetasInvalidasError) as erro:
        montar(repo_cliente, "dev", tmp_path / "dist", base_dir=base_dir)
    assert "__FEED_PUBLIC_BASE_URL__" in str(erro.value)
    assert "Product" in str(erro.value)
    assert "fake-dev" not in str(erro.value)


def test_removido_ausente_segue_sem_erro(
    repo_cliente: Path, base_dir: Path, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    escrever(repo_cliente, "metadados.yaml", config_yaml(removidos=["Rental:access:Nada"]))
    with caplog.at_level(logging.WARNING):
        manifesto = montar(repo_cliente, "dev", tmp_path / "dist", base_dir=base_dir)
    assert "Product" in manifesto["documentos"]
    assert "Rental:access:Nada" in caplog.text


def test_artefato_acima_de_16_mib_falha_com_o_tamanho(repo_cliente: Path, base_dir: Path, tmp_path: Path) -> None:
    escrever(repo_cliente, "delta/Product/hook/scriptAfterSave.js", "/*" + "x" * (16 * 1024 * 1024) + "*/\n")
    with pytest.raises(MetasInvalidasError) as erro:
        montar(repo_cliente, "dev", tmp_path / "dist", base_dir=base_dir)
    assert "bytes" in str(erro.value)
    assert "16777216" in str(erro.value)


def test_modulo_do_cliente_com_nome_da_base_sem_nao_migrados_falha(
    repo_cliente: Path, base_dir: Path, tmp_path: Path
) -> None:
    escrever(repo_cliente, "modulos/Product/document.json", {"_id": "Product", "type": "document"})
    with pytest.raises(MetasInvalidasError, match="naoMigrados"):
        montar(repo_cliente, "dev", tmp_path / "dist", base_dir=base_dir)


def test_tag_da_base_inexistente_falha_nomeando_a_tag(
    repo_cliente: Path, repo_git_com_tag, tmp_path: Path
) -> None:
    repo_git = repo_git_com_tag("base-metas/v0.9.0")
    with pytest.raises(MetasInvalidasError) as erro:
        montar(repo_cliente, "dev", tmp_path / "dist", base_repo=str(repo_git))
    assert "base-metas/v1.0.0" in str(erro.value)


def test_baixa_a_base_da_tag_do_metadados_yaml(repo_cliente: Path, repo_git_com_tag, base_dir: Path, tmp_path: Path) -> None:
    repo_git = repo_git_com_tag("base-metas/v1.0.0")
    baixado = montar(repo_cliente, "dev", tmp_path / "git", base_repo=str(repo_git))
    local = montar(repo_cliente, "dev", tmp_path / "local", base_dir=base_dir)
    assert baixado["sha256Total"] == local["sha256Total"]


def test_cli_montar_grava_o_artefato_e_falha_com_codigo_1(
    repo_cliente: Path, base_dir: Path, tmp_path: Path
) -> None:
    runner = CliRunner()
    saida = tmp_path / "dist"
    ok = runner.invoke(
        cli, ["metas", "montar", str(repo_cliente), "--ambiente", "dev", "--saida", str(saida), "--base-dir", str(base_dir)]
    )
    assert ok.exit_code == 0, ok.output
    assert (saida / "manifesto.json").is_file()
    escrever(repo_cliente, "delta/Fantasma/document.json", {})
    falha = runner.invoke(
        cli, ["metas", "montar", str(repo_cliente), "--ambiente", "dev", "--saida", str(saida), "--base-dir", str(base_dir)]
    )
    assert falha.exit_code == 1
    assert "Fantasma" in falha.output

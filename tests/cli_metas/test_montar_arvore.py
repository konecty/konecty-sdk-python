"""`metas montar --arvore`: a montagem também sai como árvore no layout da base (MBD-10, T24).

Os testes de hook do cliente leem `<Módulo>/hook/<campo>.js` e `<Módulo>/document.json`. Com
`--arvore`, eles leem o metadado montado, e não uma cópia mantida à mão. A garantia é a ida e
volta: `ler_arvore(arvore) == itens.json`, documento a documento.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from KonectySdkPython.cli import cli
from KonectySdkPython.cli.metas.arvore import ler_arvore
from KonectySdkPython.cli.metas.erros import MetasInvalidasError
from KonectySdkPython.cli.metas.montar import montar

from apoio_metas import PRODUCT_SCRIPT, config_yaml, escrever


def itens_por_id(saida: Path) -> dict:
    return {item["_id"]: item for item in json.loads((saida / "itens.json").read_text("utf-8"))}


def _cliente_com_delta(repo: Path) -> None:
    escrever(repo, "metadados.yaml", config_yaml(removidos=["Product:access:Corretor"]))
    escrever(repo, "delta/Product/document.json", {"fields": {"site": None}})
    escrever(repo, "delta/Product/hook/scriptAfterSave.js", "/* cliente */\nreturn __SITE_URL__;\n")
    escrever(repo, "delta/Product/access/Gerente Gestão de Imóveis.json", {"_id": "Product:access:Gerente", "type": "access"})
    escrever(repo, "modulos/Imovel360/document.json", {"_id": "Imovel360", "type": "document"})
    escrever(repo, "modulos/Imovel360/hook/validationData.json", {"office": {"document": "Office"}})
    escrever(repo, "modulos/Imovel360/view/Default.json", {"_id": "Imovel360:view:Default", "type": "view"})


def test_arvore_tem_o_layout_da_base_com_hooks_em_arquivo(
    repo_cliente: Path, base_dir: Path, tmp_path: Path
) -> None:
    _cliente_com_delta(repo_cliente)
    arvore = tmp_path / "arvore"
    montar(repo_cliente, "prod", tmp_path / "dist", base_dir=base_dir, arvore=arvore)

    assert (arvore / "Product/hook/scriptBeforeValidation.js").read_text("utf-8") == PRODUCT_SCRIPT
    assert (arvore / "Product/hook/scriptAfterSave.js").read_text("utf-8") == "/* cliente */\nreturn https://example.invalid;\n"
    assert json.loads((arvore / "Product/hook/validationData.json").read_text("utf-8")) == {
        "user": {"document": "User", "fields": "_id"}
    }
    produto = json.loads((arvore / "Product/document.json").read_text("utf-8"))
    assert "site" not in produto["fields"]
    assert not {"scriptBeforeValidation", "scriptAfterSave", "validationData"} & set(produto)
    assert (arvore / "Product/access/Gerente Gestão de Imóveis.json").is_file()
    assert not (arvore / "Product/access/Corretor.json").exists()
    assert (arvore / "Product/list/Default.json").is_file()
    assert json.loads((arvore / "Imovel360/hook/validationData.json").read_text("utf-8")) == {
        "office": {"document": "Office"}
    }
    assert (arvore / "Imovel360/view/Default.json").is_file()
    assert (arvore / "Opportunity/view/Default.json").is_file()


def test_ler_arvore_do_montado_devolve_os_itens_do_artefato(
    repo_cliente: Path, base_dir: Path, tmp_path: Path
) -> None:
    _cliente_com_delta(repo_cliente)
    saida = tmp_path / "dist"
    arvore = tmp_path / "arvore"
    montar(repo_cliente, "dev", saida, base_dir=base_dir, arvore=arvore)
    lida = ler_arvore(arvore, placeholders="manter")
    assert dict(lida) == itens_por_id(saida)


def test_arvore_traz_o_namespace_do_ambiente(repo_cliente: Path, base_dir: Path, tmp_path: Path) -> None:
    arvore = tmp_path / "arvore"
    montar(repo_cliente, "dev", tmp_path / "dist", base_dir=base_dir, arvore=arvore)
    namespace = json.loads((arvore / "Namespace.json").read_text("utf-8"))
    assert namespace == json.loads((tmp_path / "dist/namespace.json").read_text("utf-8"))
    assert namespace["siteUrl"] == "https://dev.example.invalid"


def test_arvore_nao_muda_o_artefato(repo_cliente: Path, base_dir: Path, tmp_path: Path) -> None:
    _cliente_com_delta(repo_cliente)
    sem = montar(repo_cliente, "dev", tmp_path / "a", base_dir=base_dir, versao="v1")
    com = montar(repo_cliente, "dev", tmp_path / "b", base_dir=base_dir, versao="v1", arvore=tmp_path / "arvore")
    assert sem == com
    for nome in ("itens.json", "namespace.json", "manifesto.json"):
        assert (tmp_path / "a" / nome).read_bytes() == (tmp_path / "b" / nome).read_bytes(), nome


def test_remontar_na_mesma_arvore_apaga_o_que_saiu_da_montagem(
    repo_cliente: Path, base_dir: Path, tmp_path: Path
) -> None:
    arvore = tmp_path / "arvore"
    escrever(repo_cliente, "modulos/Imovel360/document.json", {"_id": "Imovel360", "type": "document"})
    montar(repo_cliente, "dev", tmp_path / "dist", base_dir=base_dir, arvore=arvore)
    assert (arvore / "Imovel360/document.json").is_file()
    (repo_cliente / "modulos/Imovel360/document.json").unlink()
    montar(repo_cliente, "dev", tmp_path / "dist", base_dir=base_dir, arvore=arvore)
    assert not (arvore / "Imovel360").exists()


def test_arvore_em_pasta_alheia_nao_vazia_falha_sem_apagar(
    repo_cliente: Path, base_dir: Path, tmp_path: Path
) -> None:
    alheia = tmp_path / "meu-trabalho"
    escrever(alheia, "importante.txt", "não apague")
    with pytest.raises(MetasInvalidasError, match="meu-trabalho"):
        montar(repo_cliente, "dev", tmp_path / "dist", base_dir=base_dir, arvore=alheia)
    assert (alheia / "importante.txt").read_text("utf-8") == "não apague"


def test_cli_montar_com_arvore(repo_cliente: Path, base_dir: Path, tmp_path: Path) -> None:
    arvore = tmp_path / "dist/arvore"
    resultado = CliRunner().invoke(
        cli,
        [
            "metas", "montar", str(repo_cliente), "--ambiente", "prod", "--saida", str(tmp_path / "dist"),
            "--base-dir", str(base_dir), "--arvore", str(arvore),
        ],
    )
    assert resultado.exit_code == 0, resultado.output
    assert (arvore / "Product/document.json").is_file()
    assert (arvore / "Product/hook/scriptBeforeValidation.js").is_file()
    assert str(arvore) in resultado.output

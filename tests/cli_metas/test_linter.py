"""T16: `metas linter` (MBD-05, MBD-12.3): um teste por regra."""

from __future__ import annotations

from pathlib import Path

from apoio_metas import PRODUCT_SCRIPT, config_yaml, escrever
from click.testing import CliRunner

from KonectySdkPython.cli import cli
from KonectySdkPython.cli.metas.linter import linter


def regras(achados: list) -> list:
    return sorted((a.nivel, a.regra, a.arquivo) for a in achados)


def test_delta_que_so_difere_passa_limpo(repo_cliente: Path, base_dir: Path) -> None:
    escrever(repo_cliente, "delta/Product/document.json", {"fields": {"status": {"options": {"Vendido": {}}}, "site": None}})
    escrever(repo_cliente, "delta/Product/hook/scriptBeforeValidation.js", "/* outro */\n")
    escrever(repo_cliente, "delta/Product/access/Novo.json", {"_id": "Product:access:Novo", "type": "access"})
    assert linter(repo_cliente, base_dir) == []


def test_patch_que_repete_valor_da_base_falha(repo_cliente: Path, base_dir: Path) -> None:
    escrever(repo_cliente, "delta/Product/document.json", {"name": "Product", "fields": {"code": {"type": "autoNumber"}}})
    achados = linter(repo_cliente, base_dir)
    assert regras(achados) == [
        ("erro", "repete-base", "delta/Product/document.json"),
        ("erro", "repete-base", "delta/Product/document.json"),
    ]
    mensagens = " ".join(a.mensagem for a in achados)
    assert "name" in mensagens and "fields.code.type" in mensagens


def test_hook_js_igual_ao_da_base_falha(repo_cliente: Path, base_dir: Path) -> None:
    escrever(repo_cliente, "delta/Product/hook/scriptBeforeValidation.js", PRODUCT_SCRIPT)
    assert regras(linter(repo_cliente, base_dir)) == [
        ("erro", "repete-base", "delta/Product/hook/scriptBeforeValidation.js")
    ]


def test_hook_json_que_repete_a_base_falha(repo_cliente: Path, base_dir: Path) -> None:
    escrever(repo_cliente, "delta/Product/hook/validationData.json", {"user": {"document": "User"}})
    assert regras(linter(repo_cliente, base_dir)) == [
        ("erro", "repete-base", "delta/Product/hook/validationData.json")
    ]


def test_patch_vazio_falha(repo_cliente: Path, base_dir: Path) -> None:
    escrever(repo_cliente, "delta/Product/list/Default.json", {})
    assert regras(linter(repo_cliente, base_dir)) == [("erro", "repete-base", "delta/Product/list/Default.json")]


def test_null_em_chave_que_a_base_removeu_e_conflito(repo_cliente: Path, base_dir: Path) -> None:
    escrever(repo_cliente, "delta/Product/document.json", {"fields": {"campoQueSaiu": None}})
    achados = linter(repo_cliente, base_dir)
    assert regras(achados) == [("erro", "conflito-base", "delta/Product/document.json")]
    assert "fields.campoQueSaiu" in achados[0].mensagem


def test_patch_parcial_em_campo_que_a_base_removeu_e_conflito(repo_cliente: Path, base_dir: Path) -> None:
    escrever(repo_cliente, "delta/Product/document.json", {"fields": {"campoQueSaiu": {"label": {"pt_BR": "X"}}}})
    assert regras(linter(repo_cliente, base_dir)) == [("erro", "conflito-base", "delta/Product/document.json")]


def test_campo_novo_inteiro_do_cliente_nao_e_conflito(repo_cliente: Path, base_dir: Path) -> None:
    escrever(repo_cliente, "delta/Product/document.json", {"fields": {"novo": {"type": "text"}}})
    assert linter(repo_cliente, base_dir) == []


def test_campo_novo_em_access_nao_exige_type(repo_cliente: Path, base_dir: Path) -> None:
    # Em access, `fields.<campo>` é permissão ({"READ": {...}}), não definição de campo: não tem
    # `type`. A regra "campo novo sem type" é só de document. Achado na migração da Aux (fase 5):
    # 1.814 falsos erros, todos em access.
    escrever(
        base_dir,
        "Product/access/Corretor.json",
        {"_id": "Product:access:Corretor", "type": "access", "fields": {"code": {"READ": {"allow": True}}}},
    )
    escrever(
        repo_cliente,
        "delta/Product/access/Corretor.json",
        {"fields": {"novo": {"READ": {"allow": True}, "UPDATE": {"allow": False}}}},
    )
    assert linter(repo_cliente, base_dir) == []


def test_ordem_em_fields_nao_e_campo_novo(repo_cliente: Path, base_dir: Path) -> None:
    # `"$ordem"` é marcador do patch (ordem das chaves), não campo: não pode cair na regra de
    # campo novo sem `type` nem em nenhuma outra.
    escrever(repo_cliente, "delta/Product/document.json", {"fields": {"novo": {"type": "text"}, "$ordem": ["novo"]}})
    assert linter(repo_cliente, base_dir) == []


def test_modulo_do_cliente_com_nome_de_modulo_da_base_e_conflito(repo_cliente: Path, base_dir: Path) -> None:
    escrever(repo_cliente, "modulos/Opportunity/document.json", {"_id": "Opportunity", "type": "document"})
    assert regras(linter(repo_cliente, base_dir)) == [("erro", "conflito-base", "modulos/Opportunity")]


def test_modulo_declarado_em_nao_migrados_nao_e_conflito(repo_cliente: Path, base_dir: Path) -> None:
    escrever(repo_cliente, "metadados.yaml", config_yaml(naoMigrados=["Opportunity"]))
    escrever(repo_cliente, "modulos/Opportunity/document.json", {"_id": "Opportunity", "type": "document"})
    assert linter(repo_cliente, base_dir) == []


def test_array_inteiro_igual_ao_da_base_so_avisa(repo_cliente: Path, base_dir: Path) -> None:
    escrever(base_dir, "Product/view/Default.json", {"_id": "Product:view:Default", "type": "view", "visuals": [1, 2]})
    escrever(repo_cliente, "delta/Product/view/Default.json", {"visuals": [1, 2]})
    assert regras(linter(repo_cliente, base_dir)) == [("aviso", "array-igual", "delta/Product/view/Default.json")]


def test_cli_sai_com_1_com_erro_e_0_so_com_aviso(repo_cliente: Path, base_dir: Path) -> None:
    runner = CliRunner()
    escrever(base_dir, "Product/view/Default.json", {"_id": "Product:view:Default", "type": "view", "visuals": [1]})
    escrever(repo_cliente, "delta/Product/view/Default.json", {"visuals": [1]})
    aviso = runner.invoke(cli, ["metas", "linter", str(repo_cliente), "--base-dir", str(base_dir)])
    assert aviso.exit_code == 0, aviso.output
    assert "0 erros, 1 avisos" in aviso.output
    escrever(repo_cliente, "delta/Product/document.json", {"name": "Product"})
    erro = runner.invoke(cli, ["metas", "linter", str(repo_cliente), "--base-dir", str(base_dir)])
    assert erro.exit_code == 1
    assert "repete-base" in erro.output


def test_patch_vazio_em_objeto_que_a_base_tem_falha(repo_cliente: Path, base_dir: Path) -> None:
    escrever(repo_cliente, "delta/Product/document.json", {"fields": {"code": {}, "novoVazio": {"type": "text", "x": {}}}})
    achados = linter(repo_cliente, base_dir)
    assert regras(achados) == [("erro", "repete-base", "delta/Product/document.json")]
    assert "fields.code" in achados[0].mensagem

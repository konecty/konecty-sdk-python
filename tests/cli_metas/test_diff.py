"""T17: `metas diff` (MBD-04): criado, removido, chave alterada, hook alterado, sem diferença."""

from __future__ import annotations

from pathlib import Path

import pytest
from apoio_metas import escrever
from click.testing import CliRunner

from KonectySdkPython.cli import cli
from KonectySdkPython.cli.metas.diff import diff
from KonectySdkPython.cli.metas.montar import montar


@pytest.fixture
def artefato_a(repo_cliente: Path, base_dir: Path, tmp_path: Path) -> Path:
    montar(repo_cliente, "dev", tmp_path / "a", base_dir=base_dir, versao="v1")
    return tmp_path / "a"


def montar_b(repo: Path, base_dir: Path, tmp_path: Path) -> Path:
    montar(repo, "dev", tmp_path / "b", base_dir=base_dir, versao="v2")
    return tmp_path / "b"


def test_sem_diferenca(artefato_a: Path, repo_cliente: Path, base_dir: Path, tmp_path: Path) -> None:
    b = montar_b(repo_cliente, base_dir, tmp_path)
    texto = diff(artefato_a, b)
    assert "sem diferença" in texto
    assert "acme v1" in texto and "acme v2" in texto
    assert "Sem diferença." in diff(artefato_a, b, markdown=True)


def test_documento_criado(artefato_a: Path, repo_cliente: Path, base_dir: Path, tmp_path: Path) -> None:
    escrever(repo_cliente, "modulos/Imovel360/document.json", {"_id": "Imovel360", "type": "document"})
    texto = diff(artefato_a, montar_b(repo_cliente, base_dir, tmp_path))
    assert "+ Imovel360" in texto
    assert "1 criados, 0 removidos, 0 alterados" in texto


def test_documento_removido(artefato_a: Path, repo_cliente: Path, base_dir: Path, tmp_path: Path) -> None:
    escrever(repo_cliente, "metadados.yaml", "cliente: acme\nbase: base-metas/v1.0.0\nremovidos: [Product:access:Corretor]\n")
    texto = diff(artefato_a, montar_b(repo_cliente, base_dir, tmp_path))
    assert "- Product:access:Corretor" in texto
    assert "0 criados, 1 removidos, 0 alterados" in texto


def test_chave_alterada_por_campo(artefato_a: Path, repo_cliente: Path, base_dir: Path, tmp_path: Path) -> None:
    escrever(repo_cliente, "delta/Product/document.json", {"fields": {"site": None, "status": {"label": "S"}}, "icon": "home"})
    texto = diff(artefato_a, montar_b(repo_cliente, base_dir, tmp_path))
    assert "~ Product: fields.site, fields.status, icon" in texto


def test_hook_alterado(artefato_a: Path, repo_cliente: Path, base_dir: Path, tmp_path: Path) -> None:
    escrever(repo_cliente, "delta/Product/hook/scriptBeforeValidation.js", "/* novo */\n")
    b = montar_b(repo_cliente, base_dir, tmp_path)
    assert "~ Product: scriptBeforeValidation (hook)" in diff(artefato_a, b)
    assert "`scriptBeforeValidation (hook)`" in diff(artefato_a, b, markdown=True)


def test_namespace_alterado(artefato_a: Path, repo_cliente: Path, base_dir: Path, tmp_path: Path) -> None:
    escrever(repo_cliente, "delta/Namespace.json", {"mcpUserEnabled": True})
    assert "~ Namespace: mcpUserEnabled" in diff(artefato_a, montar_b(repo_cliente, base_dir, tmp_path))


def test_markdown_tem_tabela_por_documento(artefato_a: Path, repo_cliente: Path, base_dir: Path, tmp_path: Path) -> None:
    escrever(repo_cliente, "modulos/Imovel360/document.json", {"_id": "Imovel360", "type": "document"})
    escrever(repo_cliente, "delta/Product/document.json", {"fields": {"site": None}})
    texto = diff(artefato_a, montar_b(repo_cliente, base_dir, tmp_path), markdown=True)
    assert "| Documento | Mudança | Chaves |" in texto
    assert "| `Imovel360` | criado | |" in texto
    assert "| `Product` | alterado | `fields.site` |" in texto


def test_cli_diff(artefato_a: Path, repo_cliente: Path, base_dir: Path, tmp_path: Path) -> None:
    escrever(repo_cliente, "delta/Product/document.json", {"icon": "home"})
    b = montar_b(repo_cliente, base_dir, tmp_path)
    resultado = CliRunner().invoke(cli, ["metas", "diff", str(artefato_a), str(b), "--markdown"])
    assert resultado.exit_code == 0, resultado.output
    assert "| `Product` | alterado | `icon` |" in resultado.output

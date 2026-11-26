"""Fixtures do `konecty-cli metas`: uma base pequena e um repositório de cliente."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable

import pytest
from apoio_metas import NAMESPACE_BASE, OPPORTUNITY, PRODUCT, PRODUCT_SCRIPT, Conteudo, config_yaml, escrever


@pytest.fixture
def base_dir(tmp_path: Path) -> Path:
    raiz = tmp_path / "base"
    escrever(raiz, "Namespace.json", NAMESPACE_BASE)
    escrever(raiz, "Product/document.json", PRODUCT)
    escrever(raiz, "Product/hook/scriptBeforeValidation.js", PRODUCT_SCRIPT)
    escrever(raiz, "Product/hook/validationData.json", {"user": {"document": "User", "fields": "_id"}})
    escrever(raiz, "Product/list/Default.json", {"_id": "Product:list:Default", "type": "list", "columns": {"code": {"visible": True}}})
    escrever(raiz, "Product/access/Corretor.json", {"_id": "Product:access:Corretor", "type": "access", "fieldDefaults": {"isReadable": True}})
    escrever(raiz, "Product/access/Default.json", {"_id": "Product:access:Default", "type": "access", "fieldDefaults": {"isReadable": True}})
    escrever(raiz, "Opportunity/document.json", OPPORTUNITY)
    escrever(raiz, "Opportunity/view/Default.json", {"_id": "Opportunity:view:Default", "type": "view", "url": "__SITE_URL__/op"})
    return raiz


@pytest.fixture
def repo_cliente(tmp_path: Path) -> Path:
    raiz = tmp_path / "cliente"
    escrever(raiz, "metadados.yaml", config_yaml())
    escrever(raiz, "env/dev.env", "SITE_URL=https://dev.example.invalid\nSMTP_PASS=fake-dev\n")
    escrever(raiz, "env/prod.env", "SITE_URL=https://example.invalid\nSMTP_PASS=fake-prod\n")
    return raiz


@pytest.fixture
def repo_git_com_tag(tmp_path: Path, base_dir: Path) -> Callable[[str], Path]:
    """Repositório Git local com `metadata/base` igual a `base_dir`, sob a tag pedida."""

    def criar(tag: str) -> Path:
        repo = tmp_path / "konecty-git"
        (repo / "metadata").mkdir(parents=True)
        subprocess.run(["cp", "-R", str(base_dir), str(repo / "metadata" / "base")], check=True)
        git = ["git", "-c", "user.name=teste", "-c", "user.email=teste@example.invalid", "-c", "commit.gpgsign=false", "-c", "tag.gpgsign=false"]
        subprocess.run([*git, "init", "-q", str(repo)], check=True)
        subprocess.run([*git, "-C", str(repo), "add", "."], check=True)
        subprocess.run([*git, "-C", str(repo), "commit", "-q", "-m", "base"], check=True)
        subprocess.run([*git, "-C", str(repo), "tag", tag], check=True)
        return repo

    return criar


@pytest.fixture
def escrever_arquivo() -> Callable[[Path, str, Conteudo], Path]:
    return escrever

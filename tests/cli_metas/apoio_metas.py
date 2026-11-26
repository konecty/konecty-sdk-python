"""Apoio aos testes do `konecty-cli metas`: escrita de arquivos e os metas da base de teste."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Union

import yaml

Conteudo = Union[str, dict, list]


def escrever(raiz: Path, relativo: str, conteudo: Conteudo) -> Path:
    caminho = raiz / relativo
    caminho.parent.mkdir(parents=True, exist_ok=True)
    texto = conteudo if isinstance(conteudo, str) else json.dumps(conteudo, ensure_ascii=False, indent=2)
    caminho.write_text(texto, encoding="utf-8")
    return caminho


PRODUCT = {
    "_id": "Product",
    "type": "document",
    "name": "Product",
    "fields": {
        "code": {"type": "autoNumber", "label": {"pt_BR": "Código"}},
        "status": {"type": "picklist", "options": {"Ativo": {"pt_BR": "Ativo"}}},
        "site": {"type": "url", "label": {"pt_BR": "Site"}},
    },
}
PRODUCT_SCRIPT = "/* base */\nreturn { success: true };\n"
OPPORTUNITY = {"_id": "Opportunity", "type": "document", "name": "Opportunity", "fields": {"name": {"type": "text"}}}
NAMESPACE_BASE = {
    "_id": "Namespace",
    "name": "konecty",
    "type": "namespace",
    "ns": "__TENANT_KEY__",
    "siteUrl": "__SITE_URL__",
    "emailServers": {"default": {"auth": {"pass": "__SMTP_PASS__"}}},
}


def config_yaml(**extra: object) -> str:
    dados = {"cliente": "acme", "base": "base-metas/v1.0.0", "konecty": ">=3.19.0"}
    dados.update(extra)
    return yaml.safe_dump(dados, allow_unicode=True, sort_keys=False)

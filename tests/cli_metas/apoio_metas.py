"""Apoio aos testes do `konecty-cli metas`: escrita de arquivos e os metas da base de teste."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import yaml
from aiohttp import web

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


TOKEN = "fake-pat-metaapply-nao-e-real-0123456789"
HOOKS = ("scriptBeforeValidation", "validationScript", "scriptAfterSave", "validationData")


class KonectyFalso:
    def __init__(self) -> None:
        self.metas: Dict[str, Dict[str, Any]] = {}
        self.namespace: Dict[str, Any] = {"_id": "Namespace", "type": "namespace", "ns": "acme"}
        self.requisicoes: List[Dict[str, Any]] = []
        self.falhas: List[int] = []
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
        if request.path.startswith("/api/admin/meta/"):
            # Como o core: as rotas de admin de meta recusam o PAT da service account.
            return web.Response(text="Unauthorized", status=401)
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
            return web.json_response(self._plano(itens, corpo.get("hookMode"), corpo.get("namespacePatch")))
        for item in itens:
            self.metas[item["_id"]] = item
        if corpo.get("namespacePatch"):
            self.namespace.update(corpo["namespacePatch"])
        return web.json_response(
            {"applied": len(itens), "created": 0, "updated": 0, "deleted": 0, "warnings": [], "preservedHooks": self.preserved_hooks}
        )

    def _plano(
        self, itens: List[Dict[str, Any]], hook_mode: Optional[str], namespace_patch: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
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
        if namespace_patch is not None:
            # Como o core (applyBulk.ts): as chaves do patch cujo valor difere do Namespace gravado.
            plano["namespace"] = {
                "keys": sorted(k for k, v in namespace_patch.items() if self.namespace.get(k) != v)
            }
        return {"applied": 0, "created": 0, "updated": 0, "deleted": 0, "warnings": [], "preservedHooks": {}, "plan": plano}

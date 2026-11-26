"""Leitura de uma árvore de metas como o `fsLoad` do Konecty monta.

Regra de `Konecty/src/imports/meta/loadMetaObjects.ts:251-271`: ao lado de cada `document.json`,
`hook/<nome>.js` vira string e `hook/<nome>.json` vira objeto, no campo `<nome>` do meta. O
`POST /api/document` em lote grava esses campos quando vêm dentro do item.

Portado de `crm-imobiliario-interativo/cronjobs/bootstrap/src/bootstrap/metas.py`
(`carregar_metas`, `_hooks_do_documento`).
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, Literal

from .erros import MetasInvalidasError

logger = logging.getLogger("konecty.cli.metas.arvore")

#: Os campos de hook que o Konecty aceita (`src/imports/meta/metaAdmin/hooks.ts`, HOOK_FIELDS).
HOOK_FIELDS = ("scriptBeforeValidation", "validationScript", "scriptAfterSave", "validationData")
#: Placeholder de tenant (`__TENANT_KEY__`). Minúsculas (`__tests__`) não são placeholder.
PLACEHOLDER_RE = re.compile(r"__[A-Z0-9_]+__")
#: O Namespace da raiz não é um meta do lote: vai por `namespacePatch` (ver `montar`).
NAMESPACE_ARQUIVO = "Namespace.json"

ModoPlaceholder = Literal["ignorar", "manter"]


class Arvore(Dict[str, Dict[str, Any]]):
    """`_id` → meta, com hooks embutidos. `origens[_id]` é o arquivo, relativo à raiz."""

    def __init__(self) -> None:
        super().__init__()
        self.origens: Dict[str, Path] = {}

    def modulo(self, meta_id: str) -> str:
        """O módulo do meta: a primeira pasta do arquivo de origem."""
        origem = self.origens[meta_id]
        return origem.parts[0] if len(origem.parts) > 1 else origem.stem


def _tem_placeholder(texto: str, caminho: Path, raiz: Path, modo: ModoPlaceholder) -> bool:
    if modo == "ignorar" and PLACEHOLDER_RE.search(texto):
        logger.warning("ignorando %s (placeholder __X__ não resolvido)", caminho.relative_to(raiz))
        return True
    return False


def _hooks_do_documento(documento: Path, raiz: Path, modo: ModoPlaceholder) -> Dict[str, Any]:
    pasta = documento.parent / "hook"
    if not pasta.is_dir():
        return {}
    hooks: Dict[str, Any] = {}
    for arquivo in sorted(pasta.iterdir()):
        if arquivo.suffix not in (".js", ".json"):
            continue
        if arquivo.stem not in HOOK_FIELDS:
            raise MetasInvalidasError(
                f"hook de nome inválido em {arquivo}: válidos são {', '.join(HOOK_FIELDS)}"
            )
        texto = arquivo.read_text(encoding="utf-8")
        if _tem_placeholder(texto, arquivo, raiz, modo):
            continue
        if arquivo.suffix == ".js":
            hooks[arquivo.stem] = texto
            continue
        try:
            hooks[arquivo.stem] = json.loads(texto)
        except json.JSONDecodeError as exc:
            raise MetasInvalidasError(f"JSON inválido em {arquivo}: {exc.msg}") from None
    return hooks


def _oculto(relativo: Path) -> bool:
    return any(parte.startswith(".") for parte in relativo.parts)


def ler_arvore(raiz: Path, *, placeholders: ModoPlaceholder = "ignorar") -> Arvore:
    """Os metas de `raiz` (document, view, list, access, pivot, card...), por `_id`.

    - `document.json` sai com os hooks da pasta `hook/` ao lado.
    - `Namespace.json` da raiz fica de fora; JSON sem `_id` é ignorado com aviso.
    - `placeholders="ignorar"` (padrão do bootstrap) pula arquivo com `__X__`; `"manter"` lê o
      arquivo como está, para quem resolve os tokens depois (`metas montar`).
    - Dois arquivos com o mesmo `_id` falham nomeando os dois.
    """
    raiz = Path(raiz)
    if not raiz.is_dir():
        raise MetasInvalidasError(f"pasta de metas ausente: {raiz}")
    arvore = Arvore()
    for caminho in sorted(raiz.rglob("*.json")):
        relativo = caminho.relative_to(raiz)
        if _oculto(relativo) or "hook" in relativo.parts[:-1]:
            continue
        if relativo == Path(NAMESPACE_ARQUIVO):
            continue
        texto = caminho.read_text(encoding="utf-8")
        if _tem_placeholder(texto, caminho, raiz, placeholders):
            continue
        try:
            meta = json.loads(texto)
        except json.JSONDecodeError as exc:
            raise MetasInvalidasError(f"JSON inválido em {caminho}: {exc.msg}") from None
        if not isinstance(meta, dict) or "_id" not in meta:
            logger.warning("ignorando %s (sem _id)", relativo)
            continue
        meta_id = str(meta["_id"])
        if meta_id in arvore:
            raise MetasInvalidasError(
                f"_id {meta_id} repetido em {raiz / arvore.origens[meta_id]} e {caminho}"
            )
        if caminho.name == "document.json":
            meta.update(_hooks_do_documento(caminho, raiz, placeholders))
        arvore[meta_id] = meta
        arvore.origens[meta_id] = relativo
    return arvore

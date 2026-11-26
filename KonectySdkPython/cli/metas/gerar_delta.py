"""`metas gerar-delta`: migra uma cópia completa de metadado para base + delta (MBD-10).

A partir da `metadata/base` e da cópia do cliente, escreve no repositório do cliente:

- `delta/<caminho da base>.json`: Merge Patch de cada meta que a cópia muda (só se mudar);
- `delta/<caminho da cópia>.json`: meta novo num módulo da base, inteiro;
- `delta/<Módulo>/hook/<nome>.js|.json`: hook diferente da base (`.js` inteiro, `.json` patch);
  hook que a base tem e a cópia não vira `"<nome>": null` no patch do `document.json`;
- `modulos/<Módulo>/...`: módulo que a base não tem, copiado como está;
- `metadados.yaml`: `cliente`, `base`, `removidos` (os `_id` da base ausentes na cópia, E2).

O `Namespace.json` da cópia não é migrado: ele carrega valores por ambiente e segredos, que vão
para `env/<ambiente>.env` e `delta/Namespace.json` à mão.

Garantia: `montar(gerar_delta(base, cópia)) == ler_arvore(cópia)`, documento a documento.
"""

from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .arvore import HOOK_FIELDS, NAMESPACE_ARQUIVO, Arvore, ler_arvore
from .erros import MetasInvalidasError
from .patch import gerar_patch
from .repositorio import ARQUIVO_CONFIG, ConfigCliente, escrever_config

logger = logging.getLogger("konecty.cli.metas.gerar_delta")


@dataclass
class ResumoDelta:
    patches: List[str] = field(default_factory=list)
    novos: List[str] = field(default_factory=list)
    hooks: List[str] = field(default_factory=list)
    modulos: List[str] = field(default_factory=list)
    removidos: List[str] = field(default_factory=list)
    iguais: int = 0


def _json(valor: Any) -> str:
    return json.dumps(valor, ensure_ascii=False, indent=2) + "\n"


def _gravar(raiz: Path, relativo: Path, texto: str) -> None:
    destino = raiz / relativo
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(texto, encoding="utf-8")


def _sem_hooks(meta: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in meta.items() if k not in HOOK_FIELDS}


def _hooks_do_delta(
    saida: Path, modulo_dir: Path, base_meta: Dict[str, Any], copia_meta: Dict[str, Any], patch: Dict[str, Any]
) -> List[str]:
    """Escreve os hooks que diferem; põe `null` no patch para o hook que a cópia tirou."""
    escritos: List[str] = []
    for hook in HOOK_FIELDS:
        if hook not in copia_meta:
            if hook in base_meta:
                patch[hook] = None
            continue
        valor = copia_meta[hook]
        if hook in base_meta and base_meta[hook] == valor and type(base_meta[hook]) is type(valor):
            continue
        if isinstance(valor, str):
            relativo = modulo_dir / "hook" / f"{hook}.js"
            _gravar(saida / "delta", relativo, valor)
        else:
            relativo = modulo_dir / "hook" / f"{hook}.json"
            _gravar(saida / "delta", relativo, _json(gerar_patch(base_meta.get(hook), valor)))
        escritos.append(relativo.as_posix())
    return escritos


def _copiar_modulo(copia_raiz: Path, arvore: Arvore, meta_id: str, saida: Path) -> None:
    relativo = arvore.origens[meta_id]
    destino = saida / "modulos" / relativo
    destino.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(copia_raiz / relativo, destino)
    if relativo.name != "document.json":
        return
    pasta_hook = (copia_raiz / relativo).parent / "hook"
    if not pasta_hook.is_dir():
        return
    for arquivo in sorted(pasta_hook.iterdir()):
        if arquivo.suffix in (".js", ".json") and arquivo.stem in HOOK_FIELDS:
            alvo = destino.parent / "hook" / arquivo.name
            alvo.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(arquivo, alvo)


def gerar_delta(
    base_dir: Path,
    copia_dir: Path,
    saida: Path,
    *,
    cliente: str,
    base_tag: str,
    konecty: Optional[str] = None,
) -> ResumoDelta:
    base_dir, copia_dir, saida = Path(base_dir), Path(copia_dir), Path(saida)
    for existente in (ARQUIVO_CONFIG, "delta", "modulos"):
        if (saida / existente).exists():
            raise MetasInvalidasError(f"{saida / existente} já existe: gerar-delta não sobrescreve")
    base = ler_arvore(base_dir, placeholders="manter")
    copia = ler_arvore(copia_dir, placeholders="manter")
    modulos_base = {base.modulo(meta_id) for meta_id in base}
    caminhos_base = {origem: meta_id for meta_id, origem in base.origens.items()}
    resumo = ResumoDelta()
    saida.mkdir(parents=True, exist_ok=True)

    for meta_id in sorted(copia):
        modulo = copia.modulo(meta_id)
        meta = copia[meta_id]
        if modulo not in modulos_base:
            _copiar_modulo(copia_dir, copia, meta_id, saida)
            if modulo not in resumo.modulos:
                resumo.modulos.append(modulo)
            continue

        if meta_id in base:
            relativo = base.origens[meta_id]
            base_meta = base[meta_id]
        else:
            relativo = copia.origens[meta_id]
            if relativo in caminhos_base:
                raise MetasInvalidasError(
                    f"{copia_dir / relativo}: _id {meta_id} ocupa o caminho de {caminhos_base[relativo]} na base"
                )
            base_meta = {}

        hooks: List[str] = []
        if relativo.name == "document.json":
            patch = gerar_patch(_sem_hooks(base_meta), _sem_hooks(meta))
            hooks = _hooks_do_delta(saida, relativo.parent, base_meta, meta, patch)
            resumo.hooks.extend(hooks)
        else:
            patch = gerar_patch(base_meta, meta)

        if meta_id not in base:
            _gravar(saida / "delta", relativo, _json(patch))
            resumo.novos.append(meta_id)
        elif patch or hooks:
            if patch:
                _gravar(saida / "delta", relativo, _json(patch))
            resumo.patches.append(meta_id)
        else:
            resumo.iguais += 1

    resumo.removidos = sorted(meta_id for meta_id in base if meta_id not in copia)
    if (copia_dir / NAMESPACE_ARQUIVO).is_file():
        logger.warning(
            "Namespace.json da cópia não migrado: leve os valores para env/<ambiente>.env e delta/Namespace.json"
        )
    escrever_config(
        saida,
        ConfigCliente(cliente=cliente, base=base_tag, konecty=konecty, removidos=resumo.removidos),
    )
    return resumo

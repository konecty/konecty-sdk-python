"""`metas diff`: compara dois artefatos por documento e por chave (MBD-04).

As chaves são as de topo do meta; `fields` desce um nível (`fields.<campo>`), que é onde mora a
maior parte das mudanças. Hooks aparecem pelo nome do campo (`scriptAfterSave`), marcados como hook.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

from .arvore import HOOK_FIELDS
from .artefato import Artefato, ler_artefato

CHAVES_DETALHADAS = ("fields",)


@dataclass
class Diferenca:
    criados: List[str] = field(default_factory=list)
    removidos: List[str] = field(default_factory=list)
    alterados: Dict[str, List[str]] = field(default_factory=dict)
    namespace: List[str] = field(default_factory=list)

    @property
    def vazia(self) -> bool:
        return not (self.criados or self.removidos or self.alterados or self.namespace)


def chaves_alteradas(a: Dict[str, Any], b: Dict[str, Any]) -> List[str]:
    chaves: List[str] = []
    for chave in sorted(set(a) | set(b)):
        if chave in a and chave in b and a[chave] == b[chave] and type(a[chave]) is type(b[chave]):
            continue
        va, vb = a.get(chave), b.get(chave)
        if chave in CHAVES_DETALHADAS and isinstance(va, dict) and isinstance(vb, dict):
            for sub in sorted(set(va) | set(vb)):
                if va.get(sub) != vb.get(sub) or (sub in va) != (sub in vb):
                    chaves.append(f"{chave}.{sub}")
            continue
        chaves.append(chave)
    return chaves


def comparar(a: Artefato, b: Artefato) -> Diferenca:
    ia, ib = a.por_id, b.por_id
    diferenca = Diferenca(
        criados=sorted(set(ib) - set(ia)),
        removidos=sorted(set(ia) - set(ib)),
        namespace=chaves_alteradas(a.namespace, b.namespace),
    )
    for meta_id in sorted(set(ia) & set(ib)):
        chaves = chaves_alteradas(ia[meta_id], ib[meta_id])
        if chaves:
            diferenca.alterados[meta_id] = chaves
    return diferenca


def _rotulo(chave: str) -> str:
    return f"{chave} (hook)" if chave in HOOK_FIELDS else chave


def _versao(artefato: Artefato) -> str:
    m = artefato.manifesto
    return f"{m.get('cliente', '?')} {m.get('versaoCliente', '?')} sobre {m.get('base', '?')} ({m.get('ambiente', '?')})"


def formatar_texto(diferenca: Diferenca, a: Artefato, b: Artefato) -> str:
    linhas = [f"de: {_versao(a)}", f"para: {_versao(b)}"]
    if diferenca.vazia:
        linhas.append("sem diferença")
        return "\n".join(linhas) + "\n"
    linhas += [f"+ {meta_id}" for meta_id in diferenca.criados]
    linhas += [f"- {meta_id}" for meta_id in diferenca.removidos]
    linhas += [
        f"~ {meta_id}: {', '.join(_rotulo(c) for c in chaves)}" for meta_id, chaves in diferenca.alterados.items()
    ]
    if diferenca.namespace:
        linhas.append(f"~ Namespace: {', '.join(diferenca.namespace)}")
    linhas.append(
        f"{len(diferenca.criados)} criados, {len(diferenca.removidos)} removidos, "
        f"{len(diferenca.alterados)} alterados" + (", Namespace alterado" if diferenca.namespace else "")
    )
    return "\n".join(linhas) + "\n"


def _celula(texto: str) -> str:
    return texto.replace("|", "\\|")


def formatar_markdown(diferenca: Diferenca, a: Artefato, b: Artefato) -> str:
    linhas = ["### Diff do metadado montado", "", f"- de: `{_versao(a)}`", f"- para: `{_versao(b)}`", ""]
    if diferenca.vazia:
        linhas.append("Sem diferença.")
        return "\n".join(linhas) + "\n"
    linhas.append(
        f"**{len(diferenca.criados)}** criados, **{len(diferenca.removidos)}** removidos, "
        f"**{len(diferenca.alterados)}** alterados" + (", Namespace alterado" if diferenca.namespace else "") + "."
    )
    linhas += ["", "| Documento | Mudança | Chaves |", "|---|---|---|"]
    linhas += [f"| `{_celula(m)}` | criado | |" for m in diferenca.criados]
    linhas += [f"| `{_celula(m)}` | removido | |" for m in diferenca.removidos]
    for meta_id, chaves in diferenca.alterados.items():
        lista = ", ".join(f"`{_celula(_rotulo(c))}`" for c in chaves)
        linhas.append(f"| `{_celula(meta_id)}` | alterado | {lista} |")
    if diferenca.namespace:
        lista = ", ".join(f"`{_celula(c)}`" for c in diferenca.namespace)
        linhas.append(f"| `Namespace` | alterado | {lista} |")
    return "\n".join(linhas) + "\n"


def diff(pasta_a: Path, pasta_b: Path, *, markdown: bool = False) -> str:
    a, b = ler_artefato(pasta_a), ler_artefato(pasta_b)
    diferenca = comparar(a, b)
    return formatar_markdown(diferenca, a, b) if markdown else formatar_texto(diferenca, a, b)

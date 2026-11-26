"""JSON Merge Patch (RFC 7386) com o marcador `{"$null": true}` (emenda E3).

- `null` no patch apaga a chave (RFC 7386).
- `{"$null": true}` grava `null` literal: é a única forma de um delta representar um valor `null`
  legítimo do cliente.
- Array é substituído inteiro (RFC 7386); `$null` dentro de array não é interpretado.

`gerar_patch(a, b)` é o inverso: `aplicar_patch(a, gerar_patch(a, b)) == b`.
"""

from __future__ import annotations

import copy
from typing import Any, Dict

NULL_MARCADOR_CHAVE = "$null"


def marcador_null() -> Dict[str, bool]:
    return {NULL_MARCADOR_CHAVE: True}


def e_marcador_null(valor: Any) -> bool:
    return isinstance(valor, dict) and valor == {NULL_MARCADOR_CHAVE: True}


def aplicar_patch(alvo: Any, patch: Any) -> Any:
    """Aplica `patch` sobre `alvo` e devolve um valor novo; nenhum dos dois é alterado."""
    if e_marcador_null(patch):
        return None
    if not isinstance(patch, dict):
        return copy.deepcopy(patch)
    resultado = copy.deepcopy(alvo) if isinstance(alvo, dict) else {}
    for chave, valor in patch.items():
        if valor is None:
            resultado.pop(chave, None)
        else:
            resultado[chave] = aplicar_patch(resultado.get(chave), valor)
    return resultado


def _codificar(valor: Any) -> Any:
    """`valor` como entra num patch sobre alvo ausente: `null` em objeto vira o marcador."""
    if valor is None:
        return marcador_null()
    if isinstance(valor, dict):
        return {chave: _codificar(item) for chave, item in valor.items()}
    return copy.deepcopy(valor)


def gerar_patch(a: Any, b: Any) -> Any:
    """O menor Merge Patch que leva `a` a `b`. Objetos iguais dão `{}`."""
    if not (isinstance(a, dict) and isinstance(b, dict)):
        return _codificar(b)
    patch: Dict[str, Any] = {}
    for chave in a:
        if chave not in b:
            patch[chave] = None
    for chave, valor in b.items():
        if chave not in a:
            patch[chave] = _codificar(valor)
        elif a[chave] != valor or type(a[chave]) is not type(valor):
            if isinstance(a[chave], dict) and isinstance(valor, dict):
                patch[chave] = gerar_patch(a[chave], valor)
            else:
                patch[chave] = _codificar(valor)
    return patch

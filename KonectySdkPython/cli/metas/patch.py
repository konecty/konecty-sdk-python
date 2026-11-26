"""JSON Merge Patch (RFC 7386) com os marcadores `{"$null": true}` (emenda E3) e `"$ordem"`.

- `null` no patch apaga a chave (RFC 7386).
- `{"$null": true}` grava `null` literal: é a única forma de um delta representar um valor `null`
  legítimo do cliente.
- `"$ordem": [chaves]` num objeto do patch fixa a ordem das chaves do resultado: as listadas vêm
  primeiro, nessa ordem; as demais seguem na ordem que tinham; chave listada que não existe é
  ignorada. O Merge Patch puro segue a ordem do alvo, e no Konecty a ordem de objeto é
  comportamento (condições de filtro, colunas de lista, campos).
- Array é substituído inteiro (RFC 7386); os marcadores dentro de array não são interpretados.

`gerar_patch(a, b)` é o inverso: `aplicar_patch(a, gerar_patch(a, b)) == b`, inclusive na ordem das
chaves de cada objeto.
"""

from __future__ import annotations

import copy
from typing import Any, Dict

NULL_MARCADOR_CHAVE = "$null"
ORDEM_CHAVE = "$ordem"


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
        if chave == ORDEM_CHAVE:
            continue
        if valor is None:
            resultado.pop(chave, None)
        else:
            resultado[chave] = aplicar_patch(resultado.get(chave), valor)
    ordem = patch.get(ORDEM_CHAVE)
    if isinstance(ordem, list):
        primeiras = [chave for chave in dict.fromkeys(ordem) if chave in resultado]
        resto = [chave for chave in resultado if chave not in primeiras]
        resultado = {chave: resultado[chave] for chave in primeiras + resto}
    return resultado


def _codificar(valor: Any) -> Any:
    """`valor` como entra num patch sobre alvo ausente: `null` em objeto vira o marcador."""
    if valor is None:
        return marcador_null()
    if isinstance(valor, dict):
        return {chave: _codificar(item) for chave, item in valor.items()}
    return copy.deepcopy(valor)


def _igual_com_ordem(a: Any, b: Any) -> bool:
    """Igualdade que também compara a ordem das chaves de cada objeto."""
    if isinstance(a, dict) and isinstance(b, dict):
        return list(a) == list(b) and all(_igual_com_ordem(a[chave], b[chave]) for chave in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_igual_com_ordem(x, y) for x, y in zip(a, b))
    return a == b and type(a) is type(b)


def gerar_patch(a: Any, b: Any) -> Any:
    """O menor Merge Patch que leva `a` a `b`, ordem das chaves inclusive. Iguais dão `{}`."""
    if not (isinstance(a, dict) and isinstance(b, dict)):
        return _codificar(b)
    patch: Dict[str, Any] = {}
    for chave in a:
        if chave not in b:
            patch[chave] = None
    for chave, valor in b.items():
        if chave not in a:
            patch[chave] = _codificar(valor)
        elif not _igual_com_ordem(a[chave], valor):
            if isinstance(a[chave], dict) and isinstance(valor, dict):
                patch[chave] = gerar_patch(a[chave], valor)
            else:
                patch[chave] = _codificar(valor)
    if list(aplicar_patch(a, patch)) != list(b):
        patch[ORDEM_CHAVE] = list(b)
    return patch

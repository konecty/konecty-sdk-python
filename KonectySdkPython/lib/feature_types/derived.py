"""Campo derivado (ADR-0025 no repo Konecty).

Campo numérico que o chamador declara numa consulta, calculado no servidor por uma
expressão sobre campos ``number``/``money`` do documento primário. Volta em todo
registro e vale em ``filter`` (operadores numéricos), ``sort`` e, na consulta
cross-module, em ``groupBy`` e ``aggregators[*].field``.

O SDK só modela e transporta: alias, aridade, limites (10 campos, profundidade 3,
10 operandos) e permissão são decididos pelo servidor, que recusa com
``DERIVED_FIELD_INVALID`` (forma) ou ``DERIVED_FIELD_UNAVAILABLE`` (permissão).
Mesma forma no SDK TypeScript: ``src/sdk/types/derived.ts``.
"""

from typing import Dict, List, Literal, Union

from pydantic import BaseModel

DerivedOp = Literal["add", "subtract", "multiply", "coalesce"]


class DerivedExpression(BaseModel):
    """Nó da expressão: ``{"op", "args"}``.

    ``args``: ``str`` = campo do documento primário (``money`` sem sufixo lê
    ``.value``), ``int``/``float`` = literal, ``DerivedExpression`` = nó aninhado.
    ``add``/``subtract``/``multiply`` ≥ 2 args (``subtract`` da esquerda para a
    direita); ``coalesce`` exatamente 2, o segundo literal.
    """

    op: DerivedOp
    args: List[Union[str, int, float, "DerivedExpression"]]


DerivedExpression.model_rebuild()

DerivedOperand = Union[str, int, float, DerivedExpression]

#: ``computed`` de ``KonectyFindParams`` e de ``CrossModuleQuery``: alias → expressão.
Computed = Dict[str, DerivedExpression]

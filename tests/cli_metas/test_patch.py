"""T13: Merge Patch RFC 7386 com marcador `$null` (E3) e o diff inverso."""

from __future__ import annotations

import copy
import random
from typing import Any

import pytest

from KonectySdkPython.cli.metas.patch import aplicar_patch, gerar_patch

# RFC 7386, apêndice A: (alvo original, patch, resultado).
APENDICE_A = [
    ({"a": "b"}, {"a": "c"}, {"a": "c"}),
    ({"a": "b"}, {"b": "c"}, {"a": "b", "b": "c"}),
    ({"a": "b"}, {"a": None}, {}),
    ({"a": "b", "b": "c"}, {"a": None}, {"b": "c"}),
    ({"a": ["b"]}, {"a": "c"}, {"a": "c"}),
    ({"a": "c"}, {"a": ["b"]}, {"a": ["b"]}),
    ({"a": {"b": "c"}}, {"a": {"b": "d", "c": None}}, {"a": {"b": "d"}}),
    ({"a": [{"b": "c"}]}, {"a": [1]}, {"a": [1]}),
    (["a", "b"], ["c", "d"], ["c", "d"]),
    ({"a": "b"}, ["c"], ["c"]),
    ({"a": "foo"}, None, None),
    ({"a": "foo"}, "bar", "bar"),
    ({"e": None}, {"a": 1}, {"e": None, "a": 1}),
    ([1, 2], {"a": "b", "c": None}, {"a": "b"}),
    ({}, {"a": {"bb": {"ccc": None}}}, {"a": {"bb": {}}}),
]


@pytest.mark.parametrize(("alvo", "patch", "esperado"), APENDICE_A)
def test_exemplos_do_apendice_a_da_rfc_7386(alvo: Any, patch: Any, esperado: Any) -> None:
    assert aplicar_patch(alvo, patch) == esperado


def test_null_apaga_a_chave() -> None:
    assert aplicar_patch({"campo": 1, "outro": 2}, {"campo": None}) == {"outro": 2}


def test_marcador_null_grava_null_literal() -> None:
    assert aplicar_patch({"campo": 1}, {"campo": {"$null": True}}) == {"campo": None}
    assert aplicar_patch({}, {"a": {"b": {"$null": True}}}) == {"a": {"b": None}}


def test_array_e_substituido_inteiro_e_marcador_dentro_dele_nao_e_interpretado() -> None:
    alvo = {"lista": [1, 2, 3]}
    assert aplicar_patch(alvo, {"lista": [9]}) == {"lista": [9]}
    assert aplicar_patch(alvo, {"lista": [{"$null": True}, None]}) == {
        "lista": [{"$null": True}, None]
    }


def test_aplicar_nao_altera_alvo_nem_patch() -> None:
    alvo = {"a": {"b": [1]}, "c": 1}
    patch = {"a": {"d": [2]}, "c": None}
    alvo_antes, patch_antes = copy.deepcopy(alvo), copy.deepcopy(patch)
    resultado = aplicar_patch(alvo, patch)
    resultado["a"]["d"].append(3)
    resultado["a"]["b"].append(4)
    assert alvo == alvo_antes
    assert patch == patch_antes


def test_gerar_patch_de_iguais_e_vazio() -> None:
    assert gerar_patch({"a": {"b": [1]}}, {"a": {"b": [1]}}) == {}


def test_gerar_patch_e_minimo_por_chave() -> None:
    a = {"fields": {"x": {"type": "text", "label": "X"}, "y": {"type": "text"}}, "name": "A"}
    b = {"fields": {"x": {"type": "text", "label": "Xis"}}, "name": "A"}
    assert gerar_patch(a, b) == {"fields": {"x": {"label": "Xis"}, "y": None}}


def test_gerar_patch_usa_marcador_para_null_legitimo() -> None:
    assert gerar_patch({"a": 1}, {"a": None}) == {"a": {"$null": True}}
    assert gerar_patch({}, {"a": {"b": None}}) == {"a": {"b": {"$null": True}}}


def test_gerar_patch_distingue_bool_de_int() -> None:
    assert aplicar_patch({"a": 1}, gerar_patch({"a": 1}, {"a": True})) == {"a": True}
    assert aplicar_patch({"a": 1}, gerar_patch({"a": 1}, {"a": True}))["a"] is True


def _valor(rng: random.Random, profundidade: int) -> Any:
    escolha = rng.randrange(8 if profundidade < 3 else 5)
    if escolha == 0:
        return None
    if escolha == 1:
        return rng.randrange(4)
    if escolha == 2:
        return rng.choice(["x", "y", ""])
    if escolha == 3:
        return rng.choice([True, False])
    if escolha == 4:
        return [rng.choice([None, 1, "z"]) for _ in range(rng.randrange(3))]
    return _objeto(rng, profundidade + 1)


def _objeto(rng: random.Random, profundidade: int = 0) -> dict:
    return {rng.choice("abcde"): _valor(rng, profundidade) for _ in range(rng.randrange(5))}


@pytest.mark.parametrize("semente", range(300))
def test_propriedade_ida_e_volta_inclusive_com_null_em_valor(semente: int) -> None:
    rng = random.Random(semente)
    a, b = _objeto(rng), _objeto(rng)
    assert aplicar_patch(a, gerar_patch(a, b)) == b


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ({"a": None}, {"a": None}),
        ({"a": None}, {}),
        ({}, {"a": None}),
        ({"a": {"b": 1}}, {"a": None}),
        ({"a": None}, {"a": {"b": None}}),
        ({"a": [None]}, {"a": [None, None]}),
    ],
)
def test_ida_e_volta_nos_casos_de_null(a: dict, b: dict) -> None:
    assert aplicar_patch(a, gerar_patch(a, b)) == b


# --------------------------------------------------------------------------- ordem das chaves
# Merge Patch (RFC 7386) não guarda ordem: o resultado segue a do alvo e a chave nova vai para o
# fim. No Konecty a ordem de objeto é comportamento (condições de filtro, colunas de lista,
# campos): a UI percorre `filter.conditions` na ordem das chaves. Achado na migração da Aux
# (fase 5): 119 documentos montados na ordem da base. `"$ordem": [chaves]` no objeto do patch
# fixa a ordem do resultado.


def _ordem(valor: Any) -> Any:
    """A árvore com a ordem de cada objeto explícita, para comparar com ordem."""
    if isinstance(valor, dict):
        return [(chave, _ordem(item)) for chave, item in valor.items()]
    if isinstance(valor, list):
        return [_ordem(item) for item in valor]
    return valor


def test_ordem_reordena_o_resultado() -> None:
    resultado = aplicar_patch({"a": 1, "b": 2, "c": 3}, {"$ordem": ["c", "a", "b"]})
    assert list(resultado) == ["c", "a", "b"]
    assert resultado == {"a": 1, "b": 2, "c": 3}


def test_ordem_vale_junto_com_mudanca_e_chave_nova() -> None:
    resultado = aplicar_patch({"a": 1, "b": 2}, {"b": 20, "z": 9, "$ordem": ["z", "b", "a"]})
    assert _ordem(resultado) == [("z", 9), ("b", 20), ("a", 1)]


def test_chave_fora_da_ordem_fica_no_fim_na_ordem_que_tinha() -> None:
    resultado = aplicar_patch({"a": 1, "b": 2, "c": 3}, {"$ordem": ["c"]})
    assert list(resultado) == ["c", "a", "b"]


def test_ordem_com_chave_que_nao_existe_e_ignorada() -> None:
    assert list(aplicar_patch({"a": 1, "b": 2}, {"$ordem": ["x", "b", "a"]})) == ["b", "a"]


def test_ordem_nao_vira_chave_do_resultado() -> None:
    assert "$ordem" not in aplicar_patch({}, {"a": {"b": 1, "$ordem": ["b"]}, "$ordem": ["a"]})["a"]
    assert "$ordem" not in aplicar_patch({"a": 1}, {"$ordem": ["a"]})


def test_gerar_patch_so_com_ordem_diferente_emite_ordem() -> None:
    assert gerar_patch({"a": 1, "b": 2}, {"b": 2, "a": 1}) == {"$ordem": ["b", "a"]}


def test_gerar_patch_de_objeto_aninhado_so_com_ordem_diferente() -> None:
    a = {"filter": {"conditions": {"status:in": 1, "code:equals": 2}}}
    b = {"filter": {"conditions": {"code:equals": 2, "status:in": 1}}}
    assert gerar_patch(a, b) == {"filter": {"conditions": {"$ordem": ["code:equals", "status:in"]}}}


def test_gerar_patch_sem_ordem_quando_o_merge_ja_da_a_ordem() -> None:
    assert gerar_patch({"a": 1}, {"a": 1, "b": 2}) == {"b": 2}
    assert gerar_patch({"a": 1, "b": 2}, {"a": 1, "b": 3}) == {"b": 3}
    assert gerar_patch({"a": 1, "b": 2}, {"a": 1, "b": 2}) == {}


def test_gerar_patch_com_chave_nova_fora_do_fim_emite_ordem() -> None:
    assert gerar_patch({"a": 1, "c": 3}, {"a": 1, "b": 2, "c": 3}) == {"b": 2, "$ordem": ["a", "b", "c"]}


@pytest.mark.parametrize("semente", range(300))
def test_propriedade_ida_e_volta_guarda_a_ordem(semente: int) -> None:
    rng = random.Random(semente)
    a, b = _objeto(rng), _objeto(rng)
    chaves = list(b)
    rng.shuffle(chaves)
    b = {chave: b[chave] for chave in chaves}
    assert _ordem(aplicar_patch(a, gerar_patch(a, b))) == _ordem(b)

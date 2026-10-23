"""
Campo derivado (``computed``) — ADR-0025 no repo Konecty, spec ``campos-derivados`` (DRV-15).

**Paridade com o SDK TypeScript: `src/__test__/api/derivedFields.test.ts`** usa a
MESMA entrada (mesmo ``computed``, mesmo filtro pelo alias, mesmo corpo de consulta
cross-module) e espera a MESMA saída. Alterar um destes literais sem alterar o outro
arquivo quebra a paridade que o ``AGENTS.md`` do Konecty exige entre os dois SDKs.

O contrato é do servidor (``src/imports/data/derived/expression.ts`` no repo Konecty):
``computed: {alias: {"op": "add"|"subtract"|"multiply"|"coalesce", "args"}}``, com
``args`` str = campo, número = literal, objeto = nó aninhado. Em
``/rest/data/{document}/find`` vai na QUERY STRING como JSON (o body do POST continua
sendo o filtro); em ``/rest/query/json`` vai no corpo. O SDK **não** valida alias,
aridade, limites nem permissão — quem decide é o servidor (``DERIVED_FIELD_INVALID`` /
``DERIVED_FIELD_UNAVAILABLE``), e um limite copiado aqui passaria a mentir assim que o
backend mudasse. Mesma postura do ``within_radius``.

O que "mesma URL" quer dizer entre os dois SDKs
-----------------------------------------------

O TS trava a query string crua byte a byte (``URLSearchParams`` percent-encoda tudo:
``%7B``, ``%22``, ``%3A``, ``%2C``). Aqui a mesma query é montada com ``json.dumps``
(separadores com espaço) e ``yarl`` (deixa ``:`` e ``,`` sem codificar) — diferença
pré-existente a esta feature e comum a TODO parâmetro de ``find``. Por isso este
arquivo trava o VALOR decodificado e compactado contra o MESMO
``EXPECTED_COMPUTED_JSON`` do teste TS, mais os invariantes da query crua (nenhum
``{``, ``"`` ou espaço solto; ``unquote_plus(raw) == enviado``; ``filter`` antes de
``computed``) — o mesmo padrão de ``test_within_radius.py`` × ``withinRadius.test.ts``.
"""

import json
from urllib.parse import unquote_plus

import pytest
from aiohttp import web
from pydantic import ValidationError

from KonectySdkPython.lib.client import KonectyClient
from KonectySdkPython.lib.feature_types import (
    Computed,
    CrossModuleQuery,
    DerivedExpression,
)
from KonectySdkPython.lib.feature_types.cross_module_query import SortItem
from KonectySdkPython.lib.filters import (
    FilterOperator,
    KonectyFilter,
    KonectyFindParams,
)

#: ``iptuCond = tax + coalesce(condominiumAmount, 0)`` — o exemplo de referência da spec.
COMPUTED: Computed = {
    "iptuCond": DerivedExpression(
        op="add",
        args=["tax", DerivedExpression(op="coalesce", args=["condominiumAmount", 0])],
    )
}

#: Serialização exata de ``computed``. É o MESMO literal que o SDK TypeScript assevera.
EXPECTED_COMPUTED_JSON = (
    '{"iptuCond":{"op":"add","args":["tax",{"op":"coalesce","args":["condominiumAmount",0]}]}}'
)

#: Condição pelo alias, com operador numérico — é o que o servidor compila em ``$expr``.
#: ``disabled`` sai fora na comparação: o modelo pydantic sempre o emite, o TS nunca,
#: e a diferença é anterior a esta feature (ver ``test_within_radius.py``).
EXPECTED_CONDITION_JSON = '{"term":"iptuCond","operator":"less_than","value":1000}'


def _alias_filter() -> KonectyFilter:
    return KonectyFilter().add_condition("iptuCond", FilterOperator.LESS_THAN, 1000)


def _compact(value) -> str:
    return json.dumps(value, separators=(",", ":"))


def _sent_condition(sent_filter: str) -> str:
    condition = json.loads(sent_filter)["conditions"][0]
    condition.pop("disabled", None)
    return _compact(condition)


class TestClientFind:
    """``client.find`` — espelha o describe ``Client.find`` do teste TS."""

    @pytest.mark.asyncio
    async def test_find_sends_computed_in_the_query_string_next_to_filter(
        self, stub_server
    ) -> None:
        """``computed`` chega na query string com o MESMO conteúdo que o SDK TS envia."""
        stub_server.route(
            "GET", "/rest/data/Product/find", {"success": True, "data": [], "total": 0}
        )
        client = KonectyClient(base_url=stub_server.base_url, token="fake-token")

        await client.find(
            "Product", KonectyFindParams(filter=_alias_filter(), computed=COMPUTED)
        )

        query = stub_server.requests[-1]["query"]
        # Decodificado e compactado: byte a byte o literal do TS.
        assert _compact(json.loads(query["computed"])) == EXPECTED_COMPUTED_JSON
        assert _sent_condition(query["filter"]) == EXPECTED_CONDITION_JSON

        # Cru: é o que foi para a rede, e onde os dois SDKs já divergiram
        # (`+` do quote_plus contra `%20` do encodeURIComponent). Nenhum caractere do
        # JSON escapa sem codificação, o valor volta idêntico ao decodificar, e a ordem
        # dos parâmetros é a do TS: `filter` primeiro, `computed` depois.
        raw_path = stub_server.requests[-1]["raw_path"]
        assert "filter=" in raw_path and "computed=" in raw_path
        assert raw_path.index("filter=") < raw_path.index("computed=")
        assert "{" not in raw_path
        assert '"' not in raw_path
        assert " " not in raw_path
        raw_computed = raw_path.split("computed=", 1)[1].split("&", 1)[0]
        assert unquote_plus(raw_computed) == query["computed"]

    @pytest.mark.asyncio
    async def test_find_without_computed_sends_no_computed(self, stub_server) -> None:
        """Sem ``computed`` a query string é a de sempre — a opção é opt-in."""
        stub_server.route(
            "GET", "/rest/data/Product/find", {"success": True, "data": [], "total": 0}
        )
        client = KonectyClient(base_url=stub_server.base_url, token="fake-token")

        await client.find("Product", KonectyFindParams(filter=_alias_filter()))

        assert "computed" not in stub_server.requests[-1]["query"]
        assert "computed" not in stub_server.requests[-1]["raw_path"]

    @pytest.mark.asyncio
    async def test_alias_of_each_record_reaches_the_caller(self, stub_server) -> None:
        """``None`` é o valor do alias com operando vazio (semântica SQL): chega como veio."""
        stub_server.route(
            "GET",
            "/rest/data/Product/find",
            {
                "success": True,
                "data": [{"_id": "p-1", "iptuCond": 420}, {"_id": "p-2", "iptuCond": None}],
                "total": 2,
            },
        )
        client = KonectyClient(base_url=stub_server.base_url, token="fake-token")

        records = await client.find(
            "Product", KonectyFindParams(filter=_alias_filter(), computed=COMPUTED)
        )

        assert [record["iptuCond"] for record in records] == [420, None]


class TestExecuteQueryJson:
    """``execute_query_json`` — espelha o describe ``executeQueryJson`` do teste TS."""

    @pytest.mark.asyncio
    async def test_sends_computed_in_the_body_unchanged(self, stub_server) -> None:
        stub_server.route(
            "POST",
            "/rest/query/json",
            web.Response(
                body=b'{"_id":"p-1","iptuCond":420}\n',
                content_type="application/x-ndjson",
                headers={"X-Total-Count": "1"},
            ),
        )
        client = KonectyClient(base_url=stub_server.base_url, token="fake-token")
        query = CrossModuleQuery(
            document="Product",
            computed=COMPUTED,
            filter={
                "match": "and",
                "conditions": [
                    {"term": "iptuCond", "operator": "less_than", "value": 1000}
                ],
            },
            sort=[SortItem(property="iptuCond", direction="ASC")],
        )

        result = await client.execute_query_json(query)

        body = stub_server.requests[-1]["json"]
        assert _compact(body["computed"]) == EXPECTED_COMPUTED_JSON
        assert body["document"] == "Product"
        assert _compact(body["filter"]["conditions"][0]) == EXPECTED_CONDITION_JSON
        assert body["sort"] == [{"property": "iptuCond", "direction": "ASC"}]

        records = [record async for record in result.stream]
        assert records == [{"_id": "p-1", "iptuCond": 420}]
        # `result.total` NÃO é asseverado aqui, ao contrário do teste TS: o SDK lê
        # `headers.get("x-total-count")` sobre um `dict(CIMultiDict)` que preserva o
        # case `X-Total-Count` do servidor, então `total` vem `None` — bug pré-existente
        # de `StreamResponse.headers` (`lib/http.py`), comum a `execute_query_*` e
        # `find_stream`, fora do escopo desta feature e registrado para task própria.


class TestModel:
    """``DerivedExpression`` é o contrato do servidor — espelha ``tipos exportados`` no TS."""

    def test_unknown_op_is_rejected_by_the_model(self) -> None:
        # Paridade com o `@ts-expect-error` do TS: `divide` está fora do ADR-0025.
        with pytest.raises(ValidationError):
            DerivedExpression(op="divide", args=["tax", 2])  # type: ignore[arg-type]

    def test_nested_expression_is_accepted_in_find_params_and_cross_module_query(
        self,
    ) -> None:
        nested = DerivedExpression(
            op="multiply",
            args=[DerivedExpression(op="subtract", args=["price", "discount"]), 0.1],
        )

        find_params = KonectyFindParams(filter=KonectyFilter(), computed={"fee": nested})
        query = CrossModuleQuery(
            document="Product", computed={"fee": nested}, groupBy=["fee"]
        )

        assert _compact(find_params.model_dump(exclude_none=True)["computed"]) == (
            '{"fee":{"op":"multiply","args":[{"op":"subtract","args":["price","discount"]},0.1]}}'
        )
        assert query.model_dump(by_alias=True, exclude_none=True)["computed"] == (
            find_params.model_dump(exclude_none=True)["computed"]
        )

    def test_plain_dicts_are_accepted_as_expressions(self) -> None:
        """Quem monta o ``computed`` à mão (dict) chega ao mesmo JSON do modelo."""
        query = CrossModuleQuery(
            document="Product",
            computed={
                "iptuCond": {
                    "op": "add",
                    "args": ["tax", {"op": "coalesce", "args": ["condominiumAmount", 0]}],
                }
            },
        )

        assert (
            _compact(query.model_dump(by_alias=True, exclude_none=True)["computed"])
            == EXPECTED_COMPUTED_JSON
        )

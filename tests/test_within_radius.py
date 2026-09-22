"""
Operador de filtro ``within_radius``.

**Paridade com o SDK TypeScript: `src/__test__/api/withinRadius.test.ts`** usa a
MESMA entrada (mesmo termo, mesmo centro, mesmo raio, mesmos corpos de erro) e
espera a MESMA saída. Alterar um destes literais sem alterar o outro arquivo
quebra a paridade que esta feature existe para garantir.

O contrato é do servidor (``src/imports/data/filters/withinRadius.ts`` no repo
Konecty): ``value: {"center": [longitude, latitude] | {"document","_id","field"},
"radius": <metros>}``. O SDK **não** duplica a validação de faixa nem o teto de
raio — quem decide é o servidor, e um teto copiado aqui passaria a mentir assim
que o backend mudasse. Mesma postura do ``SORT_ABOVE_MAX_PAGE_SIZE``.
"""

import json
from urllib.parse import unquote_plus

import pytest

from KonectySdkPython.lib.client import KonectyClient
from KonectySdkPython.lib.exceptions import (
    WITHIN_RADIUS_CENTER_UNRESOLVED,
    WITHIN_RADIUS_INVALID_VALUE,
    KonectyAPIError,
    KonectyWithinRadiusCenterError,
    KonectyWithinRadiusValueError,
)
from KonectySdkPython.lib.filters import (
    FilterOperator,
    KonectyFilter,
    KonectyFindParams,
    within_radius_condition,
)

#: O termo é o campo ``address`` puro: o sufixo ``.geolocation`` é do servidor.
TERM = "address"

#: Porto Alegre, em ``(longitude, latitude)`` — longitude ~ -51, latitude ~ -30.
CENTER = (-51.2177, -30.0346)
RADIUS_METERS = 5000

CENTER_REF = {"document": "Development", "_id": "dev-1", "field": "address"}

#: Serialização exata da condição. É o MESMO literal que o SDK TypeScript
#: assevera em ``src/__test__/api/withinRadius.test.ts``.
#:
#: Duas diferenças estruturais **pré-existentes** a este operador separam os dois
#: SDKs e não são introduzidas aqui: o modelo pydantic sempre emite
#: ``"disabled": false`` na condição e ``"filters": []`` no filtro, e
#: ``json.dumps`` usa separadores com espaço por padrão (e o ``yarl`` deixa ``:``
#: e ``,`` sem percent-encoding no valor da query, onde o ``URLSearchParams`` do
#: TS usa ``%3A``/``%2C``). Todas valem para TODO operador, são semanticamente
#: neutras para o servidor (que faz ``JSON.parse`` do valor já decodificado), e
#: os testes abaixo isolam o que este operador de fato põe na requisição.
EXPECTED_CONDITION_JSON = (
    '{"term":"address","operator":"within_radius",'
    '"value":{"center":[-51.2177,-30.0346],"radius":5000}}'
)

EXPECTED_CENTER_REF_CONDITION_JSON = (
    '{"term":"address","operator":"within_radius",'
    '"value":{"center":{"document":"Development","_id":"dev-1","field":"address"},"radius":5000}}'
)

INVALID_VALUE_MESSAGE = (
    'Invalid value for operator within_radius on term "address": '
    "center must be an array of exactly 2 numbers, in the order [longitude, latitude]"
)

CENTER_UNRESOLVED_MESSAGE = (
    'Could not resolve the center record for operator within_radius on term "address".'
)


def _condition_json(condition) -> str:
    """Serializa a condição como o SDK TypeScript serializa a dele.

    ``disabled`` sai fora: o modelo pydantic sempre o emite, o TypeScript nunca,
    e a diferença é anterior a este operador. O que sobra — ``term``,
    ``operator`` e ``value`` — é o que este operador põe na requisição, e é isso
    que precisa bater byte a byte.
    """
    dumped = condition.model_dump(mode="json")
    dumped.pop("disabled", None)
    return json.dumps(dumped, separators=(",", ":"))


class TestWithinRadiusCondition:
    """Montagem da condição — espelha o describe homônimo no teste do TS."""

    def test_builds_term_operator_value_with_literal_center(self) -> None:
        condition = within_radius_condition(TERM, CENTER, RADIUS_METERS)

        assert condition.operator == FilterOperator.WITHIN_RADIUS
        assert condition.operator.value == "within_radius"
        assert _condition_json(condition) == EXPECTED_CONDITION_JSON

    def test_preserves_coordinate_order_longitude_first(self) -> None:
        # O erro nº 1 deste operador é inverter as duas. O teste fixa a ordem com
        # valores de sinais e magnitudes distinguíveis (-51 lng, -30 lat).
        condition = within_radius_condition(TERM, CENTER, RADIUS_METERS)
        center = condition.value["center"]

        assert center[0] == -51.2177
        assert center[1] == -30.0346

    def test_accepts_center_by_record_reference(self) -> None:
        condition = within_radius_condition(TERM, CENTER_REF, RADIUS_METERS)

        assert _condition_json(condition) == EXPECTED_CENTER_REF_CONDITION_JSON

    def test_add_within_radius_appends_the_same_condition(self) -> None:
        built = KonectyFilter().add_within_radius(TERM, CENTER, RADIUS_METERS)

        assert len(built.conditions) == 1
        assert _condition_json(built.conditions[0]) == EXPECTED_CONDITION_JSON

    def test_numeric_strings_are_not_coerced(self) -> None:
        # O servidor recusa string numérica de propósito (GEO-02). Coagir aqui
        # esconderia o erro do chamador em vez de reportá-lo.
        condition = within_radius_condition(TERM, ("-51.2177", "-30.0346"), RADIUS_METERS)

        assert condition.value["center"] == ["-51.2177", "-30.0346"]


@pytest.mark.asyncio
async def test_request_carries_the_condition_verbatim(stub_server) -> None:
    """A condição chega na query string exatamente como o SDK TS a envia."""
    stub_server.route(
        "GET", "/rest/data/Product/find", {"success": True, "data": [], "total": 0}
    )
    client = KonectyClient(base_url=stub_server.base_url, token="fake-token")
    find_filter = KonectyFilter().add_within_radius(TERM, CENTER, RADIUS_METERS)

    await client.find("Product", KonectyFindParams(filter=find_filter))

    sent_filter = stub_server.requests[-1]["query"]["filter"]
    condition = json.loads(sent_filter)["conditions"][0]
    condition.pop("disabled", None)
    assert json.dumps(condition, separators=(",", ":")) == EXPECTED_CONDITION_JSON

    # `raw_path` é o que foi para a rede — é onde a divergência de codificação
    # entre os dois SDKs já aconteceu (`+` do quote_plus contra `%20` do
    # encodeURIComponent). Nenhum caractere do JSON pode escapar sem codificação,
    # e o valor tem de voltar idêntico ao decodificar.
    raw_path = stub_server.requests[-1]["raw_path"]
    assert "filter=" in raw_path
    assert "{" not in raw_path
    assert '"' not in raw_path
    assert " " not in raw_path
    raw_filter = raw_path.split("filter=", 1)[1].split("&", 1)[0]
    assert unquote_plus(raw_filter) == sent_filter


class TestWithinRadiusErrorCodes:
    """Códigos de erro do servidor — espelha o describe homônimo no teste do TS."""

    @pytest.mark.asyncio
    async def test_invalid_value_raises_typed_error(self, stub_server) -> None:
        stub_server.route(
            "GET",
            "/rest/data/Product/find",
            {
                "success": False,
                "errors": [
                    {"message": INVALID_VALUE_MESSAGE, "code": WITHIN_RADIUS_INVALID_VALUE}
                ],
            },
            status=400,
        )
        client = KonectyClient(base_url=stub_server.base_url, token="fake-token")
        find_filter = KonectyFilter().add_within_radius(TERM, CENTER, -1)

        with pytest.raises(KonectyWithinRadiusValueError) as excinfo:
            await client.find("Product", KonectyFindParams(filter=find_filter))

        assert excinfo.value.code == "WITHIN_RADIUS_INVALID_VALUE"
        # A mensagem do servidor nomeia o termo e a chave que falhou.
        assert str(excinfo.value) == INVALID_VALUE_MESSAGE

    @pytest.mark.asyncio
    async def test_center_unresolved_raises_typed_error(self, stub_server) -> None:
        stub_server.route(
            "GET",
            "/rest/data/Product/find",
            {
                "success": False,
                "errors": [
                    {
                        "message": CENTER_UNRESOLVED_MESSAGE,
                        "code": WITHIN_RADIUS_CENTER_UNRESOLVED,
                    }
                ],
            },
            status=400,
        )
        client = KonectyClient(base_url=stub_server.base_url, token="fake-token")
        find_filter = KonectyFilter().add_within_radius(TERM, CENTER_REF, RADIUS_METERS)

        with pytest.raises(KonectyWithinRadiusCenterError) as excinfo:
            await client.find("Product", KonectyFindParams(filter=find_filter))

        assert excinfo.value.code == "WITHIN_RADIUS_CENTER_UNRESOLVED"
        assert str(excinfo.value) == CENTER_UNRESOLVED_MESSAGE

    @pytest.mark.asyncio
    async def test_both_stay_catchable_as_api_error(self, stub_server) -> None:
        """Quem já tratava KonectyAPIError continua pegando — mesma garantia do sort."""
        stub_server.route(
            "GET",
            "/rest/data/Product/find",
            {
                "success": False,
                "errors": [
                    {"message": INVALID_VALUE_MESSAGE, "code": WITHIN_RADIUS_INVALID_VALUE}
                ],
            },
            status=400,
        )
        client = KonectyClient(base_url=stub_server.base_url, token="fake-token")
        find_filter = KonectyFilter().add_within_radius(TERM, CENTER, -1)

        with pytest.raises(KonectyAPIError):
            await client.find("Product", KonectyFindParams(filter=find_filter))

    @pytest.mark.asyncio
    async def test_unknown_code_stays_generic(self, stub_server) -> None:
        stub_server.route(
            "GET",
            "/rest/data/Product/find",
            {"success": False, "errors": [{"message": "Some other failure"}]},
            status=400,
        )
        client = KonectyClient(base_url=stub_server.base_url, token="fake-token")
        find_filter = KonectyFilter().add_within_radius(TERM, CENTER, RADIUS_METERS)

        with pytest.raises(KonectyAPIError) as excinfo:
            await client.find("Product", KonectyFindParams(filter=find_filter))

        assert not isinstance(excinfo.value, KonectyWithinRadiusValueError)
        assert not isinstance(excinfo.value, KonectyWithinRadiusCenterError)

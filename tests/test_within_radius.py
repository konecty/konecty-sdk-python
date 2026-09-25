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

Assimetrias com o SDK TypeScript que são ESCOLHA, não defeito
-------------------------------------------------------------

1. **Aridade.** Aqui é ``within_radius_condition(term, center, radius)``; no TS é
   ``withinRadiusCondition(term, {center, radius})``. Mantidas assim de
   propósito: cada linguagem segue a convenção do próprio SDK — o TS passa
   objeto de opções em todo lugar, o Python passa parâmetros nomeados. O que a
   paridade exige é mesma ENTRADA → mesma SAÍDA, e é isso que os literais deste
   arquivo travam; uniformizar a forma de chamar tornaria um dos dois estranho
   na própria linguagem.
2. **Builder.** ``KonectyFilter.add_within_radius`` existe aqui porque existe uma
   classe ``KonectyFilter`` construída por encadeamento; o TS monta filtro como
   objeto literal e **não tem builder nenhum**. Inventar um lá só para este
   operador seria superfície pública nova sem caso de uso (YAGNI), e um builder
   parcial — um operador de catorze — é pior que nenhum.
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
#: **O que "byte a byte" quer dizer aqui.** A igualdade literal com o TS vale
#: para ``radius`` INTEIRO, que é o caso destes literais. Com raio ``float`` —
#: ``5000.0``, que é o tipo DECLARADO do parâmetro, e portanto caminho normal e
#: não borda — o Python emite ``"radius":5000.0`` e o TS emite ``"radius":5000``,
#: porque JavaScript tem um tipo numérico só. Ver
#: ``test_float_radius_keeps_the_float_the_caller_passed``: a divergência é
#: deliberada e semanticamente neutra, mas a afirmação de paridade literal não
#: se estende a ela.
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

#: Id de correlação de exemplo, no formato que o servidor emite: doze caracteres
#: hexadecimais (``randomUUID()`` sem hífens, truncado) quando não há tracing
#: ativo, ou o ``traceId`` de 32 caracteres do span quando há. É o MESMO literal
#: que o SDK TypeScript usa.
#:
#: Ele é o caminho de SUPORTE inteiro do ``WITHIN_RADIUS_CENTER_UNRESOLVED``: as
#: causas da falha (registro inexistente, ilegível, ou sem geolocalização) são
#: deliberadamente indistinguíveis na resposta — separá-las daria a quem não pode
#: ler o registro um oráculo de existência e de localização. A causa real fica só
#: no log do servidor, indexada por este id. Um SDK que truncasse a mensagem
#: jogaria fora a única chave que liga o relato do usuário à linha de log.
CORRELATION_ID = "7b3f2a9c41d8"

#: Mensagem REAL do servidor quando a hidratação do centro por referência falha,
#: copiada de ``src/imports/data/filters/hydrateFilterCenters.ts`` (função
#: ``unresolvedReturn``) no repo Konecty. Termina com o id de correlação.
CENTER_UNRESOLVED_MESSAGE = (
    "Could not resolve the center record for operator within_radius "
    f'on term "address". Correlation id: {CORRELATION_ID}'
)

#: A OUTRA mensagem com o mesmo código, do guard de "centro não hidratado" em
#: ``src/imports/data/filters/withinRadius.ts`` (``compileWithinRadius``): um
#: centro por referência que chega por um caminho que não hidrata (``update``,
#: ``findById``) é recusado ali, com texto próprio sobre caminhos de leitura e
#: **sem** id de correlação. São duas mensagens diferentes sob um código só, e o
#: SDK não pode assumir a forma de nenhuma das duas.
CENTER_UNRESOLVED_WRITE_PATH_MESSAGE = (
    "Could not resolve the center record for operator within_radius "
    'on term "address". A center by record reference is resolved only on read '
    "paths (find, stream/export and lookup) and is not supported here."
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
        condition = within_radius_condition(
            TERM, ("-51.2177", "-30.0346"), RADIUS_METERS
        )

        assert condition.value["center"] == ["-51.2177", "-30.0346"]

    def test_a_string_center_is_sent_whole_instead_of_being_split(self) -> None:
        """Centro em ``str`` vai intacto — ``list("12")`` daria ``["1", "2"]``.

        O SDK inventaria um par que o chamador não escreveu, e o servidor
        recusaria nomeando a coordenada em vez do tipo. O SDK TypeScript envia a
        string como veio; aqui também.
        """
        condition = within_radius_condition(TERM, "-51.2177", RADIUS_METERS)

        assert condition.value["center"] == "-51.2177"

    def test_float_radius_keeps_the_float_the_caller_passed(self) -> None:
        """Raio ``float`` sai como ``float`` — e é aqui que a paridade LITERAL para.

        ``radius: float`` é o tipo declarado do parâmetro, então ``5000.0`` é
        caminho normal e não borda. O JSON sai ``"radius":5000.0``, enquanto o
        SDK TypeScript, para a mesma chamada, sai ``"radius":5000`` — JavaScript
        tem um tipo numérico só, e ``JSON.stringify(5000.0)`` é ``5000``.

        **Não convergimos, de propósito.** Convergir exigiria o SDK converter
        ``float`` para ``int`` quando o valor é inteiro — exatamente a coerção
        silenciosa que este SDK recusa a fazer em ``center`` (ver
        ``test_numeric_strings_are_not_coerced``): o valor que vai para a rede
        deixaria de ser o valor que o chamador escreveu. E a divergência é
        semanticamente neutra: o servidor faz ``JSON.parse`` do filtro, onde
        ``5000`` e ``5000.0`` produzem o mesmo ``number``, e o schema do raio
        (``z.number().finite().positive()``) aceita os dois igualmente.

        O que este teste fixa é o ESCOPO da afirmação de paridade byte a byte:
        ela vale para raio inteiro, e não para raio float. Se algum dia o SDK
        passar a normalizar, é este teste que muda — não um comentário.
        """
        condition = within_radius_condition(TERM, CENTER, 5000.0)

        assert _condition_json(condition).endswith('"radius":5000.0}}')
        assert (
            json.loads(_condition_json(condition))["value"]["radius"] == RADIUS_METERS
        )


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


@pytest.mark.asyncio
async def test_request_carries_a_center_by_reference_verbatim(stub_server) -> None:
    """O centro POR REFERÊNCIA também passa por uma requisição de verdade.

    É um objeto aninhado dentro do valor da condição — mais chaves, mais aspas e
    um ``_id`` para escapar que o par literal não tem. Até aqui só o literal
    passava por uma requisição, nos dois SDKs. Paridade com
    ``'põe também o centro POR REFERÊNCIA na query string, sem caractere solto'``
    em ``src/__test__/api/withinRadius.test.ts``.
    """
    stub_server.route(
        "GET", "/rest/data/Product/find", {"success": True, "data": [], "total": 0}
    )
    client = KonectyClient(base_url=stub_server.base_url, token="fake-token")
    find_filter = KonectyFilter().add_within_radius(TERM, CENTER_REF, RADIUS_METERS)

    await client.find("Product", KonectyFindParams(filter=find_filter))

    sent_filter = stub_server.requests[-1]["query"]["filter"]
    condition = json.loads(sent_filter)["conditions"][0]
    condition.pop("disabled", None)
    assert (
        json.dumps(condition, separators=(",", ":"))
        == EXPECTED_CENTER_REF_CONDITION_JSON
    )

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
                    {
                        "message": INVALID_VALUE_MESSAGE,
                        "code": WITHIN_RADIUS_INVALID_VALUE,
                    }
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
        # A mensagem INTEIRA, id de correlação incluído. O id é a única chave que
        # liga o relato do usuário à linha de log com a causa real — truncar a
        # mensagem (ou reescrevê-la com um texto "amigável") apagaria o caminho de
        # suporte deste código de erro.
        assert str(excinfo.value) == CENTER_UNRESOLVED_MESSAGE
        assert f"Correlation id: {CORRELATION_ID}" in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_center_unresolved_on_write_path_keeps_its_own_message(
        self, stub_server
    ) -> None:
        """A OUTRA mensagem do mesmo código chega igualmente intacta.

        Duas mensagens, um código só. O SDK não conhece a forma de nenhuma das
        duas: repassa o que veio.
        """
        stub_server.route(
            "GET",
            "/rest/data/Product/find",
            {
                "success": False,
                "errors": [
                    {
                        "message": CENTER_UNRESOLVED_WRITE_PATH_MESSAGE,
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

        assert str(excinfo.value) == CENTER_UNRESOLVED_WRITE_PATH_MESSAGE

    @pytest.mark.asyncio
    async def test_both_stay_catchable_as_api_error(self, stub_server) -> None:
        """Quem já tratava KonectyAPIError continua pegando — mesma garantia do sort."""
        stub_server.route(
            "GET",
            "/rest/data/Product/find",
            {
                "success": False,
                "errors": [
                    {
                        "message": INVALID_VALUE_MESSAGE,
                        "code": WITHIN_RADIUS_INVALID_VALUE,
                    }
                ],
            },
            status=400,
        )
        client = KonectyClient(base_url=stub_server.base_url, token="fake-token")
        find_filter = KonectyFilter().add_within_radius(TERM, CENTER, -1)

        with pytest.raises(KonectyAPIError):
            await client.find("Product", KonectyFindParams(filter=find_filter))

    @pytest.mark.asyncio
    async def test_error_without_message_falls_back_to_the_same_default_as_ts(
        self, stub_server
    ) -> None:
        """Erro com ``code`` e sem ``message``: a frase default é a MESMA do TS.

        O TS usa ``message ?? \`Invalid value for operator ${WITHIN_RADIUS}\``` no
        construtor (``src/sdk/filters/withinRadius.ts``). Aqui, passar
        ``str(error.get("message"))`` produzia a string literal ``"None"`` — uma
        mensagem que não diz nada e diverge do outro SDK.
        """
        stub_server.route(
            "GET",
            "/rest/data/Product/find",
            {"success": False, "errors": [{"code": WITHIN_RADIUS_INVALID_VALUE}]},
            status=400,
        )
        client = KonectyClient(base_url=stub_server.base_url, token="fake-token")
        find_filter = KonectyFilter().add_within_radius(TERM, CENTER, RADIUS_METERS)

        with pytest.raises(KonectyWithinRadiusValueError) as excinfo:
            await client.find("Product", KonectyFindParams(filter=find_filter))

        assert str(excinfo.value) == "Invalid value for operator within_radius"

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

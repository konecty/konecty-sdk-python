"""
Operador de filtro ``within_radius``.

**Paridade com o SDK TypeScript: `src/__test__/api/withinRadius.test.ts`** usa a
MESMA entrada (mesmo termo, mesmo centro, mesmo raio, mesmos corpos de erro) e
espera a MESMA saída. Alterar um destes literais sem alterar o outro arquivo
quebra a paridade que esta feature existe para garantir.

O contrato é do servidor (``src/imports/data/filters/withinRadius.ts`` no repo
Konecty, Revisão 2 da spec ``geo-radius-filter``): ``value: {"lat", "lng",
"radius"} | {"record": {"document","_id","field"}, "radius"}``, raio em metros. A
forma antiga ``{"center": [lng, lat] | {...}, "radius"}`` deixou de existir. Cada
registro de ``find`` pode trazer ``_distance`` (metros, inteiro), e
``sort: [{"property": "_distance", "direction"}]`` ordena por ele. O SDK **não** duplica a validação de faixa nem o teto de
raio — quem decide é o servidor, e um teto copiado aqui passaria a mentir assim
que o backend mudasse. Mesma postura do ``SORT_ABOVE_MAX_PAGE_SIZE``.

Assimetrias com o SDK TypeScript que são ESCOLHA, não defeito
-------------------------------------------------------------

1. **Aridade.** Aqui é ``within_radius_condition(term, lat=, lng=, radius=)``; no
   TS é ``withinRadiusCondition(term, {lat, lng, radius})``. Mantidas assim de
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
    DISTANCE_SORT_UNAVAILABLE,
    WITHIN_RADIUS_CENTER_DEPTH_EXCEEDED,
    WITHIN_RADIUS_CENTER_UNRESOLVED,
    WITHIN_RADIUS_INVALID_VALUE,
    WITHIN_RADIUS_TOO_MANY_CENTERS,
    KonectyAPIError,
    KonectyDistanceSortUnavailableError,
    KonectySortLimitError,
    KonectyWithinRadiusCenterDepthError,
    KonectyWithinRadiusCenterError,
    KonectyWithinRadiusTooManyCentersError,
    KonectyWithinRadiusValueError,
    raise_for_konecty_errors,
)
from KonectySdkPython.lib.filters import (
    DISTANCE_FIELD,
    FilterOperator,
    KonectyFilter,
    KonectyFindParams,
    SortDirection,
    SortOrder,
    within_radius_condition,
)

#: O termo é o campo ``address`` puro: o sufixo ``.geolocation`` é do servidor.
TERM = "address"

#: Porto Alegre — latitude ~ -30, longitude ~ -51: sinais e magnitudes distinguíveis.
LAT = -30.0346
LNG = -51.2177
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
    '"value":{"lat":-30.0346,"lng":-51.2177,"radius":5000}}'
)

EXPECTED_CENTER_REF_CONDITION_JSON = (
    '{"term":"address","operator":"within_radius",'
    '"value":{"record":{"document":"Development","_id":"dev-1","field":"address"},"radius":5000}}'
)

#: Ordenação por distância, serializada. O SDK TypeScript assevera o MESMO JSON
#: (``EXPECTED_DISTANCE_SORT_JSON``).
EXPECTED_DISTANCE_SORT_JSON = '[{"property":"_distance","direction":"ASC"}]'

#: Mensagem de recusa de faixa no formato da Revisão 2 (nomeia a chave e a faixa,
#: GEO-12.5). Texto real do servidor, byte a byte (Konecty
#: ``src/imports/data/filters/withinRadius.ts``); o SDK repassa o texto sem
#: interpretá-lo — o que este arquivo trava é o ``code`` e a mensagem chegar
#: INTEIRA. MESMO literal do SDK TypeScript.
INVALID_VALUE_MESSAGE = (
    'Invalid value for operator within_radius on term "address": '
    "lat must be between -90 and 90"
)

#: As duas recusas de ``DISTANCE_SORT_UNAVAILABLE`` (GEO-14.3 e GEO-15.3): mesmo
#: código, mensagens distintas. Textos reais do servidor, byte a byte (Konecty
#: ``src/imports/data/filters/distance.ts``). MESMOS literais do SDK TypeScript.
DISTANCE_SORT_NO_CENTER_MESSAGE = (
    "Sorting by _distance requires exactly one within_radius condition "
    "on the AND path of the filter."
)
DISTANCE_SORT_NO_ACCESS_MESSAGE = (
    'Sorting by _distance requires unconditional read access to field "address".'
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
        condition = within_radius_condition(
            TERM, lat=LAT, lng=LNG, radius=RADIUS_METERS
        )

        assert condition.operator == FilterOperator.WITHIN_RADIUS
        assert condition.operator.value == "within_radius"
        assert _condition_json(condition) == EXPECTED_CONDITION_JSON

    def test_lat_and_lng_stay_in_the_key_that_names_them(self) -> None:
        condition = within_radius_condition(
            TERM, lat=LAT, lng=LNG, radius=RADIUS_METERS
        )

        assert condition.value["lat"] == -30.0346
        assert condition.value["lng"] == -51.2177

    def test_accepts_center_by_record_reference(self) -> None:
        condition = within_radius_condition(
            TERM, record=CENTER_REF, radius=RADIUS_METERS
        )

        assert _condition_json(condition) == EXPECTED_CENTER_REF_CONDITION_JSON

    def test_add_within_radius_appends_the_same_condition(self) -> None:
        built = KonectyFilter().add_within_radius(
            TERM, lat=LAT, lng=LNG, radius=RADIUS_METERS
        )

        assert len(built.conditions) == 1
        assert _condition_json(built.conditions[0]) == EXPECTED_CONDITION_JSON

    def test_numeric_strings_are_not_coerced(self) -> None:
        # Paridade com 'não coage string numérica — deixa o servidor recusar' em
        # ``src/__test__/api/withinRadius.test.ts``. O servidor recusa string numérica
        # de propósito (GEO-12.5). Coagir aqui esconderia o erro do chamador.
        condition = within_radius_condition(
            TERM, lat="-30.0346", lng="-51.2177", radius=RADIUS_METERS  # type: ignore[arg-type]
        )

        assert condition.value == {
            "lat": "-30.0346",
            "lng": "-51.2177",
            "radius": RADIUS_METERS,
        }

    def test_legacy_center_form_is_not_accepted(self) -> None:
        """A forma antiga não é aceita pelo builder — nem posicional, nem nomeada.

        Paridade com 'a forma antiga { center, radius } não é aceita pelo tipo' no
        SDK TypeScript, onde a trava é de compilação.
        """
        with pytest.raises(TypeError):
            within_radius_condition(TERM, (LNG, LAT), RADIUS_METERS)  # type: ignore[misc]
        with pytest.raises(TypeError):
            within_radius_condition(TERM, center=(LNG, LAT), radius=RADIUS_METERS)  # type: ignore[call-arg]
        with pytest.raises(TypeError):
            KonectyFilter().add_within_radius(TERM, (LNG, LAT), RADIUS_METERS)  # type: ignore[misc]

    def test_mixed_shape_is_forwarded_for_the_server_to_refuse(self) -> None:
        """As duas formas juntas vão ao servidor intactas, para ele nomear o problema.

        Paridade com 'repassa ao servidor, sem remontar, o valor que o tipo
        recusaria — para ele nomear a chave' em ``src/__test__/api/withinRadius.test.ts``:
        MESMA entrada, MESMO JSON. O servidor recusa com "mutually exclusive"
        (GEO-12.3); descartar uma das formas aqui trocaria essa mensagem por outra.
        """
        condition = within_radius_condition(
            TERM, lat=LAT, lng=LNG, record=CENTER_REF, radius=RADIUS_METERS
        )

        assert json.dumps(condition.value, separators=(",", ":")) == (
            '{"lat":-30.0346,"lng":-51.2177,'
            '"record":{"document":"Development","_id":"dev-1","field":"address"},'
            '"radius":5000}'
        )

    def test_float_radius_keeps_the_float_the_caller_passed(self) -> None:
        """Raio ``float`` sai como ``float`` — e é aqui que a paridade LITERAL para.

        ``radius: float`` é o tipo declarado do parâmetro, então ``5000.0`` é
        caminho normal e não borda. O JSON sai ``"radius":5000.0``, enquanto o
        SDK TypeScript, para a mesma chamada, sai ``"radius":5000`` — JavaScript
        tem um tipo numérico só, e ``JSON.stringify(5000.0)`` é ``5000``.

        **Não convergimos, de propósito.** Convergir exigiria o SDK converter
        ``float`` para ``int`` quando o valor é inteiro — exatamente a coerção
        silenciosa que este SDK recusa a fazer nas coordenadas (ver
        ``test_numeric_strings_are_not_coerced``). E a divergência é
        semanticamente neutra: o servidor faz ``JSON.parse`` do filtro, onde
        ``5000`` e ``5000.0`` produzem o mesmo ``number``.
        """
        condition = within_radius_condition(TERM, lat=LAT, lng=LNG, radius=5000.0)

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
    find_filter = KonectyFilter().add_within_radius(
        TERM, lat=LAT, lng=LNG, radius=RADIUS_METERS
    )

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
    find_filter = KonectyFilter().add_within_radius(
        TERM, record=CENTER_REF, radius=RADIUS_METERS
    )

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
        find_filter = KonectyFilter().add_within_radius(
            TERM, lat=LAT, lng=LNG, radius=-1
        )

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
        find_filter = KonectyFilter().add_within_radius(
            TERM, record=CENTER_REF, radius=RADIUS_METERS
        )

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
        find_filter = KonectyFilter().add_within_radius(
            TERM, record=CENTER_REF, radius=RADIUS_METERS
        )

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
        find_filter = KonectyFilter().add_within_radius(
            TERM, lat=LAT, lng=LNG, radius=-1
        )

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
        find_filter = KonectyFilter().add_within_radius(
            TERM, lat=LAT, lng=LNG, radius=RADIUS_METERS
        )

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
        find_filter = KonectyFilter().add_within_radius(
            TERM, lat=LAT, lng=LNG, radius=RADIUS_METERS
        )

        with pytest.raises(KonectyAPIError) as excinfo:
            await client.find("Product", KonectyFindParams(filter=find_filter))

        assert not isinstance(excinfo.value, KonectyWithinRadiusValueError)
        assert not isinstance(excinfo.value, KonectyWithinRadiusCenterError)


class TestDepthAndQuotaCodes:
    """
    Codigos acrescentados depois, quando o servidor ganhou teto de profundidade e cota
    de centros por requisicao.

    Paridade com ``src/__test__/api/withinRadius.test.ts`` no SDK TypeScript, describe
    ``within_radius: profundidade e cota de centros`` — MESMA entrada, MESMA saida.

    As mensagens saem de ``src/imports/data/filters/hydrateFilterCenters.ts`` no repo
    Konecty. Ja sao TRES textos diferentes sob o guarda-chuva de "centro nao resolvido",
    e e por isso que o SDK ramifica pelo ``code``, nunca pelo texto.
    """

    DEPTH_MESSAGE = (
        "Could not resolve the center record for operator within_radius on term "
        '"address": center hydration exceeded the maximum depth of 3.'
    )
    QUOTA_MESSAGE = (
        "Operator within_radius resolves at most 20 center records per request; "
        "this request asked for 34."
    )

    def test_depth_code_maps_preserving_the_whole_message(self) -> None:
        with pytest.raises(KonectyWithinRadiusCenterDepthError) as excinfo:
            raise_for_konecty_errors(
                [
                    {
                        "message": self.DEPTH_MESSAGE,
                        "code": WITHIN_RADIUS_CENTER_DEPTH_EXCEEDED,
                    }
                ]
            )

        assert excinfo.value.code == WITHIN_RADIUS_CENTER_DEPTH_EXCEEDED
        assert str(excinfo.value) == self.DEPTH_MESSAGE

    def test_depth_is_catchable_as_center_error(self) -> None:
        # A hierarquia e a promessa: o codigo novo nao quebra `except` que ja existia.
        with pytest.raises(KonectyWithinRadiusCenterError):
            raise_for_konecty_errors(
                [
                    {
                        "message": self.DEPTH_MESSAGE,
                        "code": WITHIN_RADIUS_CENTER_DEPTH_EXCEEDED,
                    }
                ]
            )

    def test_quota_code_maps_preserving_the_whole_message(self) -> None:
        with pytest.raises(KonectyWithinRadiusTooManyCentersError) as excinfo:
            raise_for_konecty_errors(
                [
                    {
                        "message": self.QUOTA_MESSAGE,
                        "code": WITHIN_RADIUS_TOO_MANY_CENTERS,
                    }
                ]
            )

        assert excinfo.value.code == WITHIN_RADIUS_TOO_MANY_CENTERS
        assert str(excinfo.value) == self.QUOTA_MESSAGE

    def test_quota_is_not_a_center_failure(self) -> None:
        # Se cota herdasse de CenterError, o chamador procuraria um registro culpado que
        # nao existe: a requisicao foi recusada antes de qualquer leitura.
        with pytest.raises(KonectyWithinRadiusTooManyCentersError) as excinfo:
            raise_for_konecty_errors(
                [
                    {
                        "message": self.QUOTA_MESSAGE,
                        "code": WITHIN_RADIUS_TOO_MANY_CENTERS,
                    }
                ]
            )

        assert not isinstance(excinfo.value, KonectyWithinRadiusCenterError)


def _geo_params(**kwargs) -> KonectyFindParams:
    return KonectyFindParams(
        filter=KonectyFilter().add_within_radius(
            TERM, lat=LAT, lng=LNG, radius=RADIUS_METERS
        ),
        **kwargs,
    )


def _distance_sort(direction: SortDirection = SortDirection.ASC):
    return [SortOrder(property=DISTANCE_FIELD, direction=direction)]


class TestDistanceAndSort:
    """
    Distância e ordenação por distância (Revisão 2: GEO-13, GEO-14, GEO-15, GEO-17).

    Paridade com ``src/__test__/api/withinRadius.test.ts`` no SDK TypeScript, describe
    ``within_radius: _distance e ordenação por distância`` — MESMA entrada, MESMA saída.
    """

    def test_distance_field_is_the_name_the_server_returns_and_sorts_by(self) -> None:
        assert DISTANCE_FIELD == "_distance"
        assert DISTANCE_SORT_UNAVAILABLE == "DISTANCE_SORT_UNAVAILABLE"

    @pytest.mark.asyncio
    async def test_find_with_geo_filter_and_distance_sort_sends_both_verbatim(
        self, stub_server
    ) -> None:
        """``filter`` e ``sort`` chegam com o MESMO conteúdo que o SDK TS envia.

        A query string crua não é igual byte a byte à do TS por diferenças
        pré-existentes e neutras (``json.dumps`` com espaço, ``yarl`` sem
        percent-encoding de ``:``/``,``; ver o topo deste arquivo). O que se trava é o
        valor decodificado, compactado, contra os MESMOS literais do TS, e que o
        ``sort`` passa sem transformação.
        """
        stub_server.route(
            "GET", "/rest/data/Product/find", {"success": True, "data": [], "total": 0}
        )
        client = KonectyClient(base_url=stub_server.base_url, token="fake-token")

        await client.find("Product", _geo_params(sort=_distance_sort()))

        query = stub_server.requests[-1]["query"]
        sent_filter = json.loads(query["filter"])
        condition = sent_filter["conditions"][0]
        condition.pop("disabled", None)
        assert json.dumps(condition, separators=(",", ":")) == EXPECTED_CONDITION_JSON
        assert (
            json.dumps(json.loads(query["sort"]), separators=(",", ":"))
            == EXPECTED_DISTANCE_SORT_JSON
        )

        raw_path = stub_server.requests[-1]["raw_path"]
        raw_sort = raw_path.split("sort=", 1)[1].split("&", 1)[0]
        assert unquote_plus(raw_sort) == query["sort"]
        assert "{" not in raw_path and '"' not in raw_path and " " not in raw_path

    @pytest.mark.asyncio
    async def test_distance_sort_desc_is_sent_verbatim(self, stub_server) -> None:
        """Paridade com 'Module.find aceita sort por _distance…' no SDK TS (DESC)."""
        stub_server.route(
            "GET", "/rest/data/Product/find", {"success": True, "data": [], "total": 0}
        )
        client = KonectyClient(base_url=stub_server.base_url, token="fake-token")

        await client.find(
            "Product", _geo_params(sort=_distance_sort(SortDirection.DESC))
        )

        sent_sort = json.loads(stub_server.requests[-1]["query"]["sort"])
        assert (
            json.dumps(sent_sort, separators=(",", ":"))
            == '[{"property":"_distance","direction":"DESC"}]'
        )

    @pytest.mark.asyncio
    async def test_each_record_distance_reaches_the_caller(self, stub_server) -> None:
        stub_server.route(
            "GET",
            "/rest/data/Product/find",
            {
                "success": True,
                "data": [
                    {"_id": "p-1", "_distance": 850},
                    {"_id": "p-2", "_distance": 4999},
                ],
                "total": 2,
            },
        )
        client = KonectyClient(base_url=stub_server.base_url, token="fake-token")

        records = await client.find("Product", _geo_params(sort=_distance_sort()))

        assert [record[DISTANCE_FIELD] for record in records] == [850, 4999]

    def test_distance_sort_unavailable_maps_with_code_and_message_no_center(
        self,
    ) -> None:
        with pytest.raises(KonectyDistanceSortUnavailableError) as excinfo:
            raise_for_konecty_errors(
                [
                    {
                        "message": DISTANCE_SORT_NO_CENTER_MESSAGE,
                        "code": DISTANCE_SORT_UNAVAILABLE,
                    }
                ]
            )

        assert excinfo.value.code == "DISTANCE_SORT_UNAVAILABLE"
        assert str(excinfo.value) == DISTANCE_SORT_NO_CENTER_MESSAGE

    def test_distance_sort_unavailable_other_message_arrives_intact(self) -> None:
        with pytest.raises(KonectyDistanceSortUnavailableError) as excinfo:
            raise_for_konecty_errors(
                [
                    {
                        "message": DISTANCE_SORT_NO_ACCESS_MESSAGE,
                        "code": DISTANCE_SORT_UNAVAILABLE,
                    }
                ]
            )

        assert str(excinfo.value) == DISTANCE_SORT_NO_ACCESS_MESSAGE

    def test_distance_sort_unavailable_without_message_uses_the_ts_default(
        self,
    ) -> None:
        with pytest.raises(KonectyDistanceSortUnavailableError) as excinfo:
            raise_for_konecty_errors([{"code": DISTANCE_SORT_UNAVAILABLE}])

        assert (
            str(excinfo.value) == "Sorting by _distance is not available for this query"
        )

    def test_distance_sort_unavailable_is_neither_filter_nor_page_cap_refusal(
        self,
    ) -> None:
        with pytest.raises(KonectyDistanceSortUnavailableError) as excinfo:
            raise_for_konecty_errors(
                [
                    {
                        "message": DISTANCE_SORT_NO_CENTER_MESSAGE,
                        "code": DISTANCE_SORT_UNAVAILABLE,
                    }
                ]
            )

        assert not isinstance(excinfo.value, KonectyWithinRadiusValueError)
        assert not isinstance(excinfo.value, KonectySortLimitError)
        assert isinstance(excinfo.value, KonectyAPIError)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "status",
        [400, 200],
        ids=["http-400", "http-200-before-geo-17"],
    )
    async def test_distance_sort_unavailable_raises_typed_on_find(
        self, stub_server, status: int
    ) -> None:
        """Paridade com os dois testes de ``Module.find`` (400 e 200) no SDK TS."""
        stub_server.route(
            "GET",
            "/rest/data/Product/find",
            {
                "success": False,
                "errors": [
                    {
                        "message": DISTANCE_SORT_NO_CENTER_MESSAGE,
                        "code": DISTANCE_SORT_UNAVAILABLE,
                    }
                ],
            },
            status=status,
        )
        client = KonectyClient(base_url=stub_server.base_url, token="fake-token")

        with pytest.raises(KonectyDistanceSortUnavailableError) as excinfo:
            await client.find(
                "Product",
                KonectyFindParams(filter=KonectyFilter(), sort=_distance_sort()),
            )

        assert excinfo.value.code == DISTANCE_SORT_UNAVAILABLE
        assert str(excinfo.value) == DISTANCE_SORT_NO_CENTER_MESSAGE

    @pytest.mark.asyncio
    async def test_invalid_value_in_http_200_is_typed_too(self, stub_server) -> None:
        """Até o GEO-17 estas recusas vinham em 200; o 400 está coberto acima."""
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
            status=200,
        )
        client = KonectyClient(base_url=stub_server.base_url, token="fake-token")

        with pytest.raises(KonectyWithinRadiusValueError) as excinfo:
            await client.find("Product", _geo_params())

        assert str(excinfo.value) == INVALID_VALUE_MESSAGE

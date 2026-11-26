"""T12: leitura de árvore de metas com hooks, pela regra do fsLoad do Konecty.

Mesmos casos de `crm-imobiliario-interativo/cronjobs/bootstrap/src/test/test_metas_montagem.py`,
mais nomes com espaço e acento (Foxter: `access/Gerente Gestão de Imóveis.json`).
A fixture `fixtures/metadata-base/Opportunity` é cópia de `konecty/Konecty` `metadata/base`
(origin/main 61cb1599).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from KonectySdkPython.cli.metas.arvore import HOOK_FIELDS, ler_arvore
from KonectySdkPython.cli.metas.erros import MetasInvalidasError

FIXTURE_REAL = Path(__file__).parent / "fixtures" / "metadata-base"

SCRIPT = "// comentário que a API de hook recusaria\n/* e outro */\nreturn {};\n"
VALIDATION_DATA = {"user": {"document": "User", "fields": "_id,role"}}
AFTER_SAVE = "/* depois de gravar */\nreturn { success: true };\n"
VALIDATION_SCRIPT = "/* valida */\nreturn { success: true };\n"


def escrever(raiz: Path, relativo: str, conteudo: str | dict) -> Path:
    caminho = raiz / relativo
    caminho.parent.mkdir(parents=True, exist_ok=True)
    texto = conteudo if isinstance(conteudo, str) else json.dumps(conteudo, ensure_ascii=False)
    caminho.write_text(texto, encoding="utf-8")
    return caminho


@pytest.fixture
def base(tmp_path: Path) -> Path:
    escrever(tmp_path, "Lead/document.json", {"_id": "Lead", "type": "document", "name": "Lead"})
    escrever(tmp_path, "Lead/hook/validationData.json", VALIDATION_DATA)
    escrever(tmp_path, "Lead/hook/scriptBeforeValidation.js", SCRIPT)
    escrever(tmp_path, "Lead/list/Default.json", {"_id": "Lead:list:Default", "type": "list"})
    escrever(tmp_path, "Visit/document.json", {"_id": "Visit", "type": "document", "name": "Visit"})
    escrever(tmp_path, "Visit/hook/scriptAfterSave.js", AFTER_SAVE)
    escrever(tmp_path, "Visit/hook/validationScript.js", VALIDATION_SCRIPT)
    return tmp_path


def hooks_esperados(pasta: Path) -> dict[str, object]:
    esperados: dict[str, object] = {}
    for arquivo in pasta.iterdir():
        if arquivo.stem in HOOK_FIELDS:
            texto = arquivo.read_text("utf-8")
            esperados[arquivo.stem] = texto if arquivo.suffix == ".js" else json.loads(texto)
    return esperados


def test_document_sai_com_os_hooks_js_como_string_e_json_como_objeto(base: Path) -> None:
    lead = ler_arvore(base)["Lead"]
    assert lead["scriptBeforeValidation"] == SCRIPT
    assert lead["validationData"] == VALIDATION_DATA
    assert lead["name"] == "Lead"


def test_cada_hook_field_do_diretorio_vai_ao_document_e_os_ausentes_ficam_de_fora(
    base: Path,
) -> None:
    metas = ler_arvore(base)
    for modulo in ("Lead", "Visit"):
        esperados = hooks_esperados(base / modulo / "hook")
        for campo in HOOK_FIELDS:
            if campo in esperados:
                assert metas[modulo][campo] == esperados[campo], (modulo, campo)
            else:
                assert campo not in metas[modulo], (modulo, campo)
    assert metas["Visit"]["scriptAfterSave"] == AFTER_SAVE
    assert metas["Visit"]["validationScript"] == VALIDATION_SCRIPT


def test_demais_metas_entram_por_id_sem_hooks(base: Path) -> None:
    metas = ler_arvore(base)
    assert metas["Lead:list:Default"] == {"_id": "Lead:list:Default", "type": "list"}
    assert metas.origens["Lead:list:Default"] == Path("Lead/list/Default.json")
    assert metas.modulo("Lead:list:Default") == "Lead"


def test_namespace_da_raiz_fica_de_fora(base: Path) -> None:
    escrever(base, "Namespace.json", {"_id": "Namespace", "type": "namespace"})
    assert "Namespace" not in ler_arvore(base)


def test_arquivo_com_placeholder_fica_de_fora(base: Path, caplog: pytest.LogCaptureFixture) -> None:
    escrever(base, "Tag/document.json", {"_id": "Tag", "type": "document", "x": "__TENANT_KEY__"})
    escrever(base, "Lead/hook/scriptAfterSave.js", "send('__TENANT_DOMAIN__');\n")
    with caplog.at_level(logging.WARNING):
        metas = ler_arvore(base)
    assert "Tag" not in metas
    assert "scriptAfterSave" not in metas["Lead"]
    assert "placeholder" in caplog.text


def test_placeholders_manter_le_o_arquivo_com_o_token_cru(base: Path) -> None:
    escrever(base, "Tag/document.json", {"_id": "Tag", "type": "document", "x": "__TENANT_KEY__"})
    escrever(base, "Lead/hook/scriptAfterSave.js", "send('__TENANT_DOMAIN__');\n")
    metas = ler_arvore(base, placeholders="manter")
    assert metas["Tag"]["x"] == "__TENANT_KEY__"
    assert metas["Lead"]["scriptAfterSave"] == "send('__TENANT_DOMAIN__');\n"


def test_dunder_minusculo_nao_e_placeholder_e_o_hook_entra(base: Path) -> None:
    script = "/* ver __tests__/proposta.test.ts */\nreturn { success: true };\n"
    escrever(base, "Lead/hook/scriptAfterSave.js", script)
    assert ler_arvore(base)["Lead"]["scriptAfterSave"] == script


def test_json_sem_id_fora_de_hook_e_ignorado_com_aviso(
    base: Path, caplog: pytest.LogCaptureFixture
) -> None:
    escrever(base, "Lead/extra/fragmento.json", {"sem": "id"})
    with caplog.at_level(logging.WARNING):
        metas = ler_arvore(base)
    assert set(metas) == {"Lead", "Lead:list:Default", "Visit"}
    assert "fragmento.json" in caplog.text
    assert "sem _id" in caplog.text


def test_hook_de_nome_invalido_falha_nomeando_o_arquivo(base: Path) -> None:
    ruim = escrever(base, "Lead/hook/scriptDepois.js", "return 1;\n")
    with pytest.raises(MetasInvalidasError) as erro:
        ler_arvore(base)
    assert str(ruim) in str(erro.value)


def test_json_invalido_falha_nomeando_o_arquivo(base: Path) -> None:
    ruim = escrever(base, "Lead/view/Default.json", "{ nao é json")
    with pytest.raises(MetasInvalidasError) as erro:
        ler_arvore(base)
    assert str(ruim) in str(erro.value)


def test_id_repetido_em_dois_arquivos_falha_nomeando_os_dois(base: Path) -> None:
    copia = escrever(base, "Lead/list/Copia.json", {"_id": "Lead:list:Default", "type": "list"})
    with pytest.raises(MetasInvalidasError) as erro:
        ler_arvore(base)
    assert str(copia) in str(erro.value)
    assert str(base / "Lead/list/Default.json") in str(erro.value)


def test_nome_de_arquivo_com_espaco_e_acento_entra(base: Path) -> None:
    perfil = {
        "_id": "Product:access:Gerente Gestão de Imóveis",
        "type": "access",
        "document": "Product",
        "name": "Gerente Gestão de Imóveis",
    }
    escrever(base, "Product/document.json", {"_id": "Product", "type": "document"})
    escrever(base, "Product/access/Gerente Gestão de Imóveis.json", perfil)
    metas = ler_arvore(base)
    assert metas["Product:access:Gerente Gestão de Imóveis"] == perfil
    assert metas.origens[perfil["_id"]] == Path("Product/access/Gerente Gestão de Imóveis.json")


def test_card_e_pivot_entram_como_os_demais(base: Path) -> None:
    escrever(base, "Lead/card/Default.json", {"_id": "Lead:card:Default", "type": "card"})
    escrever(base, "Lead/pivot/Default.json", {"_id": "Lead:pivot:Default", "type": "pivot"})
    metas = ler_arvore(base)
    assert metas["Lead:card:Default"]["type"] == "card"
    assert metas["Lead:pivot:Default"]["type"] == "pivot"


def test_pasta_inexistente_falha(tmp_path: Path) -> None:
    with pytest.raises(MetasInvalidasError, match="ausente"):
        ler_arvore(tmp_path / "nao-existe")


def test_metadata_base_real_monta_o_opportunity_com_os_tres_hooks() -> None:
    metas = ler_arvore(FIXTURE_REAL)
    oportunidade = metas["Opportunity"]
    hooks = FIXTURE_REAL / "Opportunity" / "hook"
    assert oportunidade["validationScript"] == (hooks / "validationScript.js").read_text("utf-8")
    assert oportunidade["scriptBeforeValidation"] == (
        hooks / "scriptBeforeValidation.js"
    ).read_text("utf-8")
    assert oportunidade["validationData"] == json.loads(
        (hooks / "validationData.json").read_text("utf-8")
    )
    assert "Opportunity:access:EquipeIsolada" in metas

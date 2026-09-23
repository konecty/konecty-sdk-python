"""
Aplicação de hooks pelo `konecty-cli apply`.

Os hooks de script (`*.js`) são texto e vão para o MetaObject como string. O
`validationData.json` é um OBJETO no core (`processValidationScript` itera
`Object.keys(validationData)`): gravado como o texto cru do arquivo, cada
caractere virava uma "entrada", cada uma um `find` sem `document` — o log
enchia de `validationData 1377: [undefined] Collection not found` e o
`validationScript` rodava sem os dados que o `validationData` deveria trazer.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from KonectySdkPython.cli.apply import DocFiles, apply_document


class FakeCollection:
    """MetaObjects em memória: só o que o apply de hooks usa."""

    def __init__(self, doc: Optional[Dict[str, Any]]) -> None:
        self.doc = doc
        self.updates: List[Dict[str, Any]] = []

    def find_one(self, query: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return self.doc

    def update_one(self, query: Dict[str, Any], update: Dict[str, Any]) -> None:
        self.updates.append(update)
        if self.doc is not None:
            self.doc.update(update["$set"])


VALIDATION_DATA = {
    "original": {
        "document": "Product",
        "fields": "_id, status",
        "filter": {
            "match": "and",
            "conditions": [{"term": "_id", "operator": "equals", "value": "$this._id"}],
        },
    }
}


def _hook_files(tmp_path: Path, files: Dict[str, str]) -> DocFiles:
    hook_dir = tmp_path / "Product" / "hook"
    hook_dir.mkdir(parents=True)
    paths = []
    for name, content in files.items():
        path = hook_dir / name
        path.write_text(content)
        paths.append(path)
    return {"document": [], "view": [], "list": [], "pivot": [], "access": [], "hook": sorted(paths)}


@pytest.mark.asyncio
async def test_validation_data_json_is_stored_as_object(tmp_path: Path) -> None:
    collection = FakeCollection({"_id": "Product", "name": "Product", "type": "document"})
    doc_files = _hook_files(tmp_path, {"validationData.json": json.dumps(VALIDATION_DATA, indent=2) + "\n"})

    applied, errors, _ = await apply_document(collection, "Product", doc_files)

    assert errors == []
    assert applied == ["✓ Product/validationData"]
    assert collection.updates == [{"$set": {"validationData": VALIDATION_DATA}}]


@pytest.mark.asyncio
async def test_script_hook_is_stored_as_text(tmp_path: Path) -> None:
    script = "return { success: true };\n"
    collection = FakeCollection({"_id": "Product", "name": "Product", "type": "document"})
    doc_files = _hook_files(tmp_path, {"validationScript.js": script})

    await apply_document(collection, "Product", doc_files)

    assert collection.updates == [{"$set": {"validationScript": script}}]


@pytest.mark.asyncio
async def test_identical_validation_data_object_is_skipped(tmp_path: Path) -> None:
    collection = FakeCollection(
        {"_id": "Product", "name": "Product", "type": "document", "validationData": VALIDATION_DATA}
    )
    doc_files = _hook_files(tmp_path, {"validationData.json": json.dumps(VALIDATION_DATA, indent=2)})

    applied, errors, skipped = await apply_document(collection, "Product", doc_files)

    assert (applied, errors) == ([], [])
    assert skipped == ["⚡ Product/validationData [identical]"]
    assert collection.updates == []


@pytest.mark.asyncio
async def test_validation_data_stored_as_string_is_repaired(tmp_path: Path) -> None:
    # Estado deixado pelo apply antigo: o texto do arquivo, idêntico byte a byte.
    content = json.dumps(VALIDATION_DATA, indent=2)
    collection = FakeCollection(
        {"_id": "Product", "name": "Product", "type": "document", "validationData": content}
    )
    doc_files = _hook_files(tmp_path, {"validationData.json": content})

    applied, _, skipped = await apply_document(collection, "Product", doc_files)

    assert skipped == []
    assert applied == ["✓ Product/validationData"]
    assert collection.doc is not None and collection.doc["validationData"] == VALIDATION_DATA


@pytest.mark.asyncio
async def test_invalid_json_hook_is_an_error_and_not_written(tmp_path: Path) -> None:
    collection = FakeCollection({"_id": "Product", "name": "Product", "type": "document"})
    doc_files = _hook_files(tmp_path, {"validationData.json": '{"original": '})

    applied, errors, _ = await apply_document(collection, "Product", doc_files)

    assert applied == []
    assert len(errors) == 1 and errors[0].startswith("✗ Product/validationData: JSON inválido")
    assert collection.updates == []

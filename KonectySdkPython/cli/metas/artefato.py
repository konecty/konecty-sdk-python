"""O artefato montado: `itens.json`, `namespace.json` e `manifesto.json`.

```
manifesto.json   # {cliente, versaoCliente, base, konectyMin, ambiente, deltaBytes, deltaPct,
                 #  naoMigrados[], removidos[], documentos: {_id: sha256}, origens: {_id: [arquivo]},
                 #  sha256Total}
itens.json       # MetaObject[] completos, hooks embutidos, placeholders resolvidos, ordenados por _id
namespace.json   # patch do Namespace do ambiente (sem metadataVersion: quem aplica acrescenta)
```

`sha256Total` é o sha256 dos bytes de `itens.json`, seguidos dos de `namespace.json`, de `\n` e do
`ambiente` do manifesto. O sha256 de
cada documento é o do JSON canônico do item (chaves ordenadas, sem espaços, UTF-8).
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import tarfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from .erros import MetasInvalidasError

ITENS = "itens.json"
NAMESPACE = "namespace.json"
MANIFESTO = "manifesto.json"
#: `bodyLimit` do `POST /api/document` (`BULK_BODY_LIMIT` no Konecty). Emenda E5.
LIMITE_BYTES = 16 * 1024 * 1024


def json_canonico(valor: Any) -> bytes:
    return json.dumps(valor, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def sha256_documento(item: Dict[str, Any]) -> str:
    return hashlib.sha256(json_canonico(item)).hexdigest()


def serializar_itens(itens: List[Dict[str, Any]]) -> bytes:
    """Um item por linha, na ordem dada: JSON válido e diff de Git legível."""
    linhas = [json.dumps(item, ensure_ascii=False, separators=(",", ":")) for item in itens]
    return ("[\n" + ",\n".join(linhas) + "\n]\n").encode() if linhas else b"[]\n"


def serializar_namespace(namespace: Dict[str, Any]) -> bytes:
    return (json.dumps(namespace, ensure_ascii=False, indent=2) + "\n").encode()


def serializar_manifesto(manifesto: Dict[str, Any]) -> bytes:
    return (json.dumps(manifesto, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def sha256_total(itens_bytes: bytes, namespace_bytes: bytes, ambiente: str) -> str:
    """O ambiente entra no hash: trocar só o `ambiente` do manifesto não pode levar um artefato de dev a prod."""
    return hashlib.sha256(itens_bytes + namespace_bytes + b"\n" + ambiente.encode("utf-8")).hexdigest()


@dataclass
class Artefato:
    manifesto: Dict[str, Any]
    itens: List[Dict[str, Any]]
    namespace: Dict[str, Any]
    itens_bytes: bytes
    namespace_bytes: bytes

    @property
    def por_id(self) -> Dict[str, Dict[str, Any]]:
        return {str(item["_id"]): item for item in self.itens}

    def sha256_confere(self) -> bool:
        ambiente = self.manifesto.get("ambiente")
        if not isinstance(ambiente, str):
            return False
        return sha256_total(self.itens_bytes, self.namespace_bytes, ambiente) == self.manifesto.get("sha256Total")


def ler_artefato(pasta: Path) -> Artefato:
    pasta = Path(pasta)
    arquivos: Dict[str, bytes] = {}
    for nome in (MANIFESTO, ITENS, NAMESPACE):
        caminho = pasta / nome
        if not caminho.is_file():
            raise MetasInvalidasError(f"artefato incompleto: {caminho} ausente")
        arquivos[nome] = caminho.read_bytes()
    try:
        manifesto = json.loads(arquivos[MANIFESTO])
        itens = json.loads(arquivos[ITENS])
        namespace = json.loads(arquivos[NAMESPACE])
    except json.JSONDecodeError as exc:
        raise MetasInvalidasError(f"artefato com JSON inválido em {pasta}: {exc.msg}") from None
    if not isinstance(itens, list) or not isinstance(namespace, dict) or not isinstance(manifesto, dict):
        raise MetasInvalidasError(f"artefato com formato inesperado em {pasta}")
    return Artefato(manifesto, itens, namespace, arquivos[ITENS], arquivos[NAMESPACE])


def escrever_tar(destino: Path, arquivos: Dict[str, bytes]) -> None:
    """`.tar.gz` byte a byte determinístico: ordem, mtime, dono e o cabeçalho gzip fixos."""
    tar_bytes = io.BytesIO()
    with tarfile.open(fileobj=tar_bytes, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for nome in sorted(arquivos):
            info = tarfile.TarInfo(f"metas/{nome}")
            info.size = len(arquivos[nome])
            info.mtime = 0
            info.mode = 0o644
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            tar.addfile(info, io.BytesIO(arquivos[nome]))
    with open(destino, "wb") as saida:
        with gzip.GzipFile(filename="", mode="wb", fileobj=saida, mtime=0) as gz:
            gz.write(tar_bytes.getvalue())

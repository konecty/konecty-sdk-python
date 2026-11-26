"""O repositório de metadado de um cliente: `metadados.yaml`, `delta/`, `modulos/`, `env/`.

```
metadados.yaml           # cliente, base (tag base-metas/vX.Y.Z), konecty, removidos, naoMigrados
delta/<Módulo>/...       # mesma árvore da base; .json = Merge Patch; hook/*.js substitui o hook
delta/Namespace.json     # Merge Patch sobre o Namespace.json da base
modulos/<Módulo>/...     # módulos só do cliente (ou cópia integral de um módulo `naoMigrados`)
env/<ambiente>.env       # valores não secretos dos placeholders __X__, por ambiente
```
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .erros import MetasInvalidasError

ARQUIVO_CONFIG = "metadados.yaml"
_LINHA_ENV = re.compile(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")


@dataclass
class ConfigCliente:
    cliente: str
    base: str
    konecty: Optional[str] = None
    versao: Optional[str] = None
    removidos: List[str] = field(default_factory=list)
    nao_migrados: List[str] = field(default_factory=list)


def _lista_de_texto(dados: Dict[str, Any], chave: str, caminho: Path) -> List[str]:
    valor = dados.get(chave) or []
    if not isinstance(valor, list) or not all(isinstance(item, str) for item in valor):
        raise MetasInvalidasError(f"{caminho}: '{chave}' tem de ser uma lista de textos")
    return list(valor)


def ler_config(repo: Path) -> ConfigCliente:
    caminho = Path(repo) / ARQUIVO_CONFIG
    if not caminho.is_file():
        raise MetasInvalidasError(f"{ARQUIVO_CONFIG} ausente em {repo}")
    try:
        dados = yaml.safe_load(caminho.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise MetasInvalidasError(f"YAML inválido em {caminho}: {exc}") from None
    if not isinstance(dados, dict):
        raise MetasInvalidasError(f"{caminho}: esperado um mapa de chaves")
    for obrigatoria in ("cliente", "base"):
        if not isinstance(dados.get(obrigatoria), str) or not dados[obrigatoria].strip():
            raise MetasInvalidasError(f"{caminho}: '{obrigatoria}' é obrigatório")
    versao = dados.get("versao")
    konecty = dados.get("konecty")
    return ConfigCliente(
        cliente=dados["cliente"].strip(),
        base=dados["base"].strip(),
        konecty=str(konecty) if konecty is not None else None,
        versao=str(versao) if versao is not None else None,
        removidos=_lista_de_texto(dados, "removidos", caminho),
        nao_migrados=_lista_de_texto(dados, "naoMigrados", caminho),
    )


def escrever_config(repo: Path, config: ConfigCliente) -> Path:
    dados: Dict[str, Any] = {"cliente": config.cliente, "base": config.base}
    if config.konecty is not None:
        dados["konecty"] = config.konecty
    if config.versao is not None:
        dados["versao"] = config.versao
    dados["removidos"] = sorted(config.removidos)
    dados["naoMigrados"] = sorted(config.nao_migrados)
    caminho = Path(repo) / ARQUIVO_CONFIG
    caminho.write_text(
        yaml.safe_dump(dados, allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )
    return caminho


def ler_env(caminho: Path) -> Dict[str, str]:
    """`KEY=VALOR` por linha; `#` comenta, `export ` e aspas em volta do valor são aceitos."""
    if not caminho.is_file():
        return {}
    valores: Dict[str, str] = {}
    for numero, linha in enumerate(caminho.read_text(encoding="utf-8").splitlines(), start=1):
        texto = linha.strip()
        if not texto or texto.startswith("#"):
            continue
        achado = _LINHA_ENV.match(texto)
        if achado is None:
            raise MetasInvalidasError(f"linha {numero} inválida em {caminho} (esperado CHAVE=VALOR)")
        chave, valor = achado.group(1), achado.group(2).strip()
        if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "'\"":
            valor = valor[1:-1]
        valores[chave] = valor
    return valores

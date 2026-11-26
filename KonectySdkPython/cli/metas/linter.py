"""`metas linter`: delta redundante e conflito com a base (MBD-05, MBD-12.3).

Regras:

- **erro** `repete-base`: o patch grava numa chave o mesmo valor que a base já tem (AC-355, 2ª
  parte); vale também para hook `.js` igual ao da base e para patch vazio `{}`.
- **erro** `conflito-base`: o patch apaga (`null`) uma chave que a base não tem; o patch de um
  `document`/`composite` mexe em `fields.<campo>` que a base não tem sem definir o campo inteiro
  (sem `type`; em `access`, `fields.<campo>` é permissão e não tem `type`); ou um módulo de
  `modulos/` tem o nome de um módulo da base e não está em `naoMigrados`.
- **aviso** `array-igual`: o patch repete uma lista inteira igual à da base (RFC 7386 substitui
  a lista inteira, então o delta não encolhe, mas também não muda nada).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Literal, Optional, Tuple

from .arvore import HOOK_FIELDS, NAMESPACE_ARQUIVO, ler_arvore
from .erros import MetasInvalidasError
from .patch import e_marcador_null
from .repositorio import ler_config

Nivel = Literal["erro", "aviso"]


@dataclass(frozen=True)
class Achado:
    nivel: Nivel
    regra: str
    arquivo: str
    mensagem: str

    def __str__(self) -> str:
        return f"{self.nivel}: {self.arquivo}: {self.mensagem} [{self.regra}]"


def _caminho(partes: Tuple[str, ...]) -> str:
    return ".".join(partes)


#: Metas cujo `fields.<campo>` é definição de campo (com `type`). Em `access`, é permissão.
TIPOS_COM_DEFINICAO_DE_CAMPO = ("document", "composite")


def _comparar(
    patch: Any,
    base: Any,
    partes: Tuple[str, ...],
    arquivo: str,
    achados: List[Achado],
    define_campos: bool = True,
) -> None:
    if not isinstance(patch, dict) or e_marcador_null(patch):
        return
    base_obj = base if isinstance(base, dict) else {}
    tem_base = isinstance(base, dict)
    for chave, valor in patch.items():
        caminho = partes + (chave,)
        existe = tem_base and chave in base_obj
        atual = base_obj.get(chave)
        if valor is None:
            if not existe:
                achados.append(
                    Achado("erro", "conflito-base", arquivo, f"{_caminho(caminho)}: apaga uma chave que a base não tem")
                )
        elif e_marcador_null(valor):
            if existe and atual is None:
                achados.append(Achado("erro", "repete-base", arquivo, f"{_caminho(caminho)}: repete o null da base"))
        elif isinstance(valor, dict):
            if valor == {} and existe and isinstance(atual, dict):
                achados.append(Achado("erro", "repete-base", arquivo, f"{_caminho(caminho)}: patch vazio"))
            elif existe and isinstance(atual, dict):
                _comparar(valor, atual, caminho, arquivo, achados, define_campos)
            elif define_campos and not existe and len(caminho) == 2 and caminho[0] == "fields" and "type" not in valor:
                achados.append(
                    Achado(
                        "erro",
                        "conflito-base",
                        arquivo,
                        f"{_caminho(caminho)}: o campo não existe na base e o patch não o define inteiro (sem type)",
                    )
                )
        elif isinstance(valor, list):
            if existe and atual == valor:
                achados.append(Achado("aviso", "array-igual", arquivo, f"{_caminho(caminho)}: lista inteira igual à da base"))
        elif existe and atual == valor and type(atual) is type(valor):
            achados.append(Achado("erro", "repete-base", arquivo, f"{_caminho(caminho)}: repete o valor da base"))


def _ler_json(caminho: Path) -> Any:
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise MetasInvalidasError(f"JSON inválido em {caminho}: {exc.msg}") from None


def linter(repo: Path, base_dir: Path) -> List[Achado]:
    repo, base_dir = Path(repo), Path(base_dir)
    config = ler_config(repo)
    base = ler_arvore(base_dir, placeholders="manter")
    por_arquivo = {origem: meta_id for meta_id, origem in base.origens.items()}
    modulos_base = {base.modulo(meta_id) for meta_id in base}
    achados: List[Achado] = []

    modulos_dir = repo / "modulos"
    if modulos_dir.is_dir():
        for pasta in sorted(p for p in modulos_dir.iterdir() if p.is_dir() and not p.name.startswith(".")):
            if pasta.name in modulos_base and pasta.name not in config.nao_migrados:
                achados.append(
                    Achado(
                        "erro",
                        "conflito-base",
                        f"modulos/{pasta.name}",
                        f"a base também tem o módulo {pasta.name}: declare-o em naoMigrados ou leve a diferença para delta/",
                    )
                )

    delta_dir = repo / "delta"
    arquivos = sorted(p for p in delta_dir.rglob("*") if p.is_file()) if delta_dir.is_dir() else []
    for caminho in arquivos:
        relativo = caminho.relative_to(delta_dir)
        if any(parte.startswith(".") for parte in relativo.parts):
            continue
        nome = f"delta/{relativo.as_posix()}"
        if "hook" in relativo.parts[:-1]:
            alvo = _alvo_do_hook(relativo, por_arquivo, base)
            if alvo is None:
                continue
            if caminho.suffix == ".js":
                if alvo == caminho.read_text(encoding="utf-8"):
                    achados.append(Achado("erro", "repete-base", nome, "hook igual ao da base"))
            elif caminho.suffix == ".json":
                _comparar_raiz(_ler_json(caminho), alvo, nome, achados)
            continue
        if caminho.suffix != ".json":
            continue
        if relativo == Path(NAMESPACE_ARQUIVO):
            arquivo_base = base_dir / NAMESPACE_ARQUIVO
            if arquivo_base.is_file():
                _comparar_raiz(_ler_json(caminho), _ler_json(arquivo_base), nome, achados)
            continue
        meta_id = por_arquivo.get(relativo)
        if meta_id is None:
            continue
        _comparar_raiz(_ler_json(caminho), base[meta_id], nome, achados)
    return achados


def _comparar_raiz(patch: Any, base: Any, nome: str, achados: List[Achado]) -> None:
    if patch == {}:
        achados.append(Achado("erro", "repete-base", nome, "patch vazio"))
        return
    tipo = base.get("type") if isinstance(base, dict) else None
    _comparar(patch, base, (), nome, achados, define_campos=tipo is None or tipo in TIPOS_COM_DEFINICAO_DE_CAMPO)


def _alvo_do_hook(relativo: Path, por_arquivo: dict, base: Any) -> Optional[Any]:
    if relativo.stem not in HOOK_FIELDS:
        return None
    meta_id = por_arquivo.get(relativo.parent.parent / "document.json")
    if meta_id is None:
        return None
    return base[meta_id].get(relativo.stem)

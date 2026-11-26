"""`metas montar`: base@tag + `delta/` + `modulos/` − `removidos`, placeholders por ambiente.

Ordem (MBD-01.1): a base; os módulos `naoMigrados` trocados pela cópia integral de `modulos/`;
os módulos só do cliente; o Merge Patch de cada arquivo do delta; a remoção dos `removidos`; a
resolução dos `__X__` por `env/<ambiente>.env`. O artefato é determinístico (MBD-02.3) e falha
acima de 16 MiB (E5).
"""

from __future__ import annotations

import io
import json
import logging
import shutil
import subprocess
import tarfile
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from . import artefato as art
from .arvore import HOOK_FIELDS, NAMESPACE_ARQUIVO, PLACEHOLDER_RE, Arvore, ler_arvore
from .erros import MetasInvalidasError
from .patch import aplicar_patch
from .repositorio import ConfigCliente, ler_config, ler_env

logger = logging.getLogger("konecty.cli.metas.montar")

BASE_REPO_PADRAO = "https://github.com/konecty/Konecty.git"
BASE_CAMINHO_NO_REPO = "metadata/base"
#: Campos que o `namespacePatch` recusa (`IMMUTABLE_NAMESPACE_FIELDS` no Konecty).
NAMESPACE_IMUTAVEIS = ("_id", "type", "ns")


@dataclass
class Montagem:
    """Resultado em memória de uma montagem, antes de virar arquivo."""

    config: ConfigCliente
    ambiente: str
    versao: str
    itens: Dict[str, Dict[str, Any]]
    namespace: Dict[str, Any]
    origens: Dict[str, List[str]]
    delta_bytes: int
    base_bytes_comuns: int
    removidos_ausentes: List[str] = field(default_factory=list)

    @property
    def delta_pct(self) -> float:
        if self.base_bytes_comuns == 0:
            return 0.0
        return round(100 * self.delta_bytes / self.base_bytes_comuns, 1)


# --------------------------------------------------------------------------- base


def _git(*args: str, cwd: Optional[Path] = None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, check=False)


def obter_base(tag: str, repo: str, destino: Path) -> Path:
    """Baixa `metadata/base` da `tag` de `repo` (URL ou caminho local) para `destino`."""
    git_dir = destino / "git"
    git_dir.mkdir(parents=True, exist_ok=True)
    _git("init", "-q", "--bare", str(git_dir))
    busca = _git("--git-dir", str(git_dir), "fetch", "-q", "--depth", "1", repo, f"refs/tags/{tag}:refs/tags/{tag}")
    if busca.returncode != 0:
        raise MetasInvalidasError(f"tag da base inexistente ou inacessível: {tag} (em {repo})")
    pacote = _git("--git-dir", str(git_dir), "archive", "--format=tar", f"refs/tags/{tag}", BASE_CAMINHO_NO_REPO)
    if pacote.returncode != 0:
        raise MetasInvalidasError(f"a tag {tag} não tem {BASE_CAMINHO_NO_REPO}")
    extraida = destino / "arvore"
    with tarfile.open(fileobj=io.BytesIO(pacote.stdout)) as tar:
        tar.extractall(extraida, filter="data")
    return extraida / BASE_CAMINHO_NO_REPO


# --------------------------------------------------------------------------- montagem


def _ler_json(caminho: Path) -> Any:
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise MetasInvalidasError(f"JSON inválido em {caminho}: {exc.msg}") from None


def _arquivos(raiz: Path) -> List[Path]:
    """Arquivos de `raiz`, relativos e ordenados, sem os ocultos."""
    if not raiz.is_dir():
        return []
    return sorted(
        p.relative_to(raiz)
        for p in raiz.rglob("*")
        if p.is_file() and not any(parte.startswith(".") for parte in p.relative_to(raiz).parts)
    )


def _e_hook(relativo: Path) -> bool:
    return "hook" in relativo.parts[:-1]


def _modulos(arvore: Arvore) -> Set[str]:
    return {arvore.modulo(meta_id) for meta_id in arvore}


def _resolver(valor: Any, env: Dict[str, str], faltando: Set[str]) -> Any:
    if isinstance(valor, str):
        def troca(achado: Any) -> str:
            token = achado.group(0)
            chave = token[2:-2]
            if chave not in env:
                faltando.add(token)
                return token
            return env[chave]

        return PLACEHOLDER_RE.sub(troca, valor)
    if isinstance(valor, dict):
        return {chave: _resolver(item, env, faltando) for chave, item in valor.items()}
    if isinstance(valor, list):
        return [_resolver(item, env, faltando) for item in valor]
    return valor


def montar_metas(
    repo: Path,
    base_raiz: Path,
    ambiente: str,
    *,
    versao: Optional[str] = None,
) -> Montagem:
    """Monta em memória. Falha com `MetasInvalidasError` nomeando o arquivo ou o token."""
    repo = Path(repo)
    config = ler_config(repo)
    base = ler_arvore(base_raiz, placeholders="manter")
    modulos_base = _modulos(base)

    itens: Dict[str, Dict[str, Any]] = {}
    origens: Dict[str, List[str]] = {}
    por_arquivo: Dict[Path, str] = {}
    modulo_de: Dict[str, str] = {}

    for modulo in config.nao_migrados:
        if not (repo / "modulos" / modulo).is_dir():
            raise MetasInvalidasError(f"naoMigrados lista {modulo}, que não está em modulos/")

    for meta_id, meta in base.items():
        modulo = base.modulo(meta_id)
        if modulo in config.nao_migrados:
            continue
        itens[meta_id] = meta
        origens[meta_id] = [f"base:{base.origens[meta_id].as_posix()}"]
        por_arquivo[base.origens[meta_id]] = meta_id
        modulo_de[meta_id] = modulo

    if (repo / "modulos").is_dir():
        so_cliente = ler_arvore(repo / "modulos", placeholders="manter")
        for meta_id, meta in so_cliente.items():
            modulo = so_cliente.modulo(meta_id)
            relativo = so_cliente.origens[meta_id]
            if modulo in modulos_base and modulo not in config.nao_migrados:
                raise MetasInvalidasError(
                    f"modulos/{relativo.as_posix()}: o módulo {modulo} também existe na base; "
                    "declare-o em naoMigrados ou leve a diferença para delta/"
                )
            if meta_id in itens:
                raise MetasInvalidasError(f"modulos/{relativo.as_posix()}: _id {meta_id} já vem da base")
            itens[meta_id] = meta
            origens[meta_id] = [f"modulos/{relativo.as_posix()}"]
            por_arquivo[relativo] = meta_id
            modulo_de[meta_id] = modulo

    modulos_presentes = set(modulo_de.values())
    delta_raiz = repo / "delta"
    delta_bytes = 0
    base_bytes_comuns = 0
    namespace_patch: Any = None
    arquivos_delta = _arquivos(delta_raiz)
    # Os patches de meta antes dos hooks: um `"hook": null` no document.json não apaga o hook
    # que o próprio delta traz.
    for relativo in sorted(arquivos_delta, key=lambda r: (_e_hook(r), r)):
        caminho = delta_raiz / relativo
        if relativo.suffix not in (".json", ".js"):
            continue
        if (base_raiz / relativo).is_file():
            delta_bytes += caminho.stat().st_size
            base_bytes_comuns += (base_raiz / relativo).stat().st_size
        if relativo == Path(NAMESPACE_ARQUIVO):
            namespace_patch = _ler_json(caminho)
            continue
        modulo = relativo.parts[0]
        if len(relativo.parts) < 2 or modulo not in modulos_presentes:
            raise MetasInvalidasError(
                f"{caminho}: o módulo {modulo} não existe na base nem em modulos/"
            )
        origem = f"delta/{relativo.as_posix()}"
        if _e_hook(relativo):
            _aplicar_hook(caminho, relativo, itens, por_arquivo, origens, origem)
            continue
        if relativo.suffix != ".json":
            raise MetasInvalidasError(f"{caminho}: fora de hook/ o delta só aceita .json")
        patch = _ler_json(caminho)
        meta_id = por_arquivo.get(relativo)
        if meta_id is not None:
            novo = aplicar_patch(itens[meta_id], patch)
            if not isinstance(novo, dict) or novo.get("_id") != itens[meta_id].get("_id"):
                raise MetasInvalidasError(f"{caminho}: o patch não pode trocar nem apagar o _id")
            itens[meta_id] = novo
            origens[meta_id].append(origem)
            continue
        novo = aplicar_patch({}, patch)
        if not isinstance(novo, dict) or "_id" not in novo:
            raise MetasInvalidasError(f"{caminho}: meta novo do delta sem _id")
        novo_id = str(novo["_id"])
        if novo_id in itens:
            raise MetasInvalidasError(
                f"{caminho}: _id {novo_id} já existe em {origens[novo_id][0]}; o patch tem de ficar no mesmo caminho"
            )
        itens[novo_id] = novo
        origens[novo_id] = [origem]
        por_arquivo[relativo] = novo_id

    removidos_ausentes: List[str] = []
    for meta_id in config.removidos:
        if itens.pop(meta_id, None) is None:
            removidos_ausentes.append(meta_id)
            logger.warning("removidos: %s não está na montagem; seguindo", meta_id)
        origens.pop(meta_id, None)

    env = ler_env(repo / "env" / f"{ambiente}.env")
    faltando: Dict[str, Set[str]] = {}
    resolvidos: Dict[str, Dict[str, Any]] = {}
    for meta_id in sorted(itens):
        tokens: Set[str] = set()
        resolvidos[meta_id] = _resolver(itens[meta_id], env, tokens)
        for token in tokens:
            faltando.setdefault(token, set()).add(meta_id)

    namespace = _montar_namespace(base_raiz, namespace_patch)
    tokens_ns: Set[str] = set()
    namespace = _resolver(namespace, env, tokens_ns)
    for token in tokens_ns:
        faltando.setdefault(token, set()).add(NAMESPACE_ARQUIVO)

    if faltando:
        detalhe = "; ".join(
            f"{token} em {', '.join(sorted(ids))}" for token, ids in sorted(faltando.items())
        )
        raise MetasInvalidasError(
            f"placeholder sem valor em env/{ambiente}.env: {detalhe}"
        )

    return Montagem(
        config=config,
        ambiente=ambiente,
        versao=versao or config.versao or "0.0.0-dev",
        itens=resolvidos,
        namespace=namespace,
        origens={meta_id: origens[meta_id] for meta_id in resolvidos},
        delta_bytes=delta_bytes,
        base_bytes_comuns=base_bytes_comuns,
        removidos_ausentes=removidos_ausentes,
    )


def _aplicar_hook(
    caminho: Path,
    relativo: Path,
    itens: Dict[str, Dict[str, Any]],
    por_arquivo: Dict[Path, str],
    origens: Dict[str, List[str]],
    origem: str,
) -> None:
    if relativo.stem not in HOOK_FIELDS or relativo.suffix not in (".js", ".json"):
        raise MetasInvalidasError(
            f"hook de nome inválido em {caminho}: válidos são {', '.join(HOOK_FIELDS)} (.js ou .json)"
        )
    documento = relativo.parent.parent / "document.json"
    meta_id = por_arquivo.get(documento)
    if meta_id is None:
        raise MetasInvalidasError(f"{caminho}: hook sem o {documento.as_posix()} correspondente")
    if relativo.suffix == ".js":
        valor: Any = caminho.read_text(encoding="utf-8")
    else:
        valor = aplicar_patch(itens[meta_id].get(relativo.stem), _ler_json(caminho))
    itens[meta_id] = {**itens[meta_id], relativo.stem: valor}
    origens[meta_id].append(origem)


def _montar_namespace(base_raiz: Path, patch: Any) -> Dict[str, Any]:
    arquivo = base_raiz / NAMESPACE_ARQUIVO
    namespace: Any = _ler_json(arquivo) if arquivo.is_file() else {}
    if patch is not None:
        namespace = aplicar_patch(namespace, patch)
    if not isinstance(namespace, dict):
        raise MetasInvalidasError("delta/Namespace.json tem de resultar num objeto")
    return {k: v for k, v in namespace.items() if k not in NAMESPACE_IMUTAVEIS}


# --------------------------------------------------------------------------- saída

#: Marca a pasta de `--arvore` como gerada pelo montador: só uma pasta com ela é recriada.
MARCA_ARVORE = ".konecty-arvore"


def _caminho_na_arvore(origem: str) -> Path:
    """`base:P`, `modulos/P` ou `delta/P` → `P`: o arquivo que deu origem ao meta."""
    for prefixo in ("base:", "modulos/", "delta/"):
        if origem.startswith(prefixo):
            return Path(origem[len(prefixo):])
    raise MetasInvalidasError(f"origem desconhecida na montagem: {origem}")


def _json_arvore(valor: Any) -> str:
    return json.dumps(valor, ensure_ascii=False, indent=2) + "\n"


def _preparar_pasta_arvore(destino: Path) -> None:
    if destino.exists():
        if not destino.is_dir():
            raise MetasInvalidasError(f"--arvore {destino} existe e não é pasta")
        if any(destino.iterdir()) and not (destino / MARCA_ARVORE).is_file():
            raise MetasInvalidasError(
                f"--arvore {destino} não está vazia e não foi gerada pelo montador "
                f"(sem {MARCA_ARVORE}); escolha outra pasta"
            )
        shutil.rmtree(destino)
    destino.mkdir(parents=True)
    (destino / MARCA_ARVORE).write_text("gerada por konecty-cli metas montar --arvore\n", encoding="utf-8")


def escrever_arvore(montagem: Montagem, destino: Path) -> None:
    """Grava a montagem no layout da base: `<Módulo>/document.json`, `view/`, `list/`, `access/`...

    Os hooks de cada `document.json` saem em `hook/<campo>.js` (texto) ou `.json` (objeto), e o
    Namespace do ambiente em `Namespace.json`. `ler_arvore(destino)` devolve `montagem.itens`.
    """
    destino = Path(destino)
    _preparar_pasta_arvore(destino)
    for meta_id in sorted(montagem.itens):
        meta = montagem.itens[meta_id]
        relativo = _caminho_na_arvore(montagem.origens[meta_id][0])
        arquivo = destino / relativo
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        if relativo.name == "document.json":
            for hook in HOOK_FIELDS:
                if hook not in meta:
                    continue
                valor = meta[hook]
                pasta = arquivo.parent / "hook"
                pasta.mkdir(exist_ok=True)
                if isinstance(valor, str):
                    (pasta / f"{hook}.js").write_text(valor, encoding="utf-8")
                else:
                    (pasta / f"{hook}.json").write_text(_json_arvore(valor), encoding="utf-8")
            meta = {chave: valor for chave, valor in meta.items() if chave not in HOOK_FIELDS}
        arquivo.write_text(_json_arvore(meta), encoding="utf-8")
    (destino / NAMESPACE_ARQUIVO).write_text(_json_arvore(montagem.namespace), encoding="utf-8")


def gerar_arquivos(montagem: Montagem, limite_bytes: int = art.LIMITE_BYTES) -> Dict[str, bytes]:
    """Os três arquivos do artefato. Falha acima de `limite_bytes` com o tamanho no erro."""
    ordenados = [montagem.itens[meta_id] for meta_id in sorted(montagem.itens)]
    itens_bytes = art.serializar_itens(ordenados)
    namespace_bytes = art.serializar_namespace(montagem.namespace)
    tamanho = len(itens_bytes) + len(namespace_bytes)
    if tamanho > limite_bytes:
        raise MetasInvalidasError(
            f"artefato com {tamanho} bytes passa do limite de {limite_bytes} bytes "
            "(bodyLimit de 16 MiB do POST /api/document)"
        )
    config = montagem.config
    manifesto = {
        "cliente": config.cliente,
        "versaoCliente": montagem.versao,
        "base": config.base,
        "konectyMin": config.konecty,
        "ambiente": montagem.ambiente,
        "deltaBytes": montagem.delta_bytes,
        "deltaPct": montagem.delta_pct,
        "naoMigrados": sorted(config.nao_migrados),
        "removidos": sorted(config.removidos),
        "documentos": {meta_id: art.sha256_documento(montagem.itens[meta_id]) for meta_id in sorted(montagem.itens)},
        "origens": {meta_id: montagem.origens[meta_id] for meta_id in sorted(montagem.origens)},
        "sha256Total": art.sha256_total(itens_bytes, namespace_bytes, montagem.ambiente),
    }
    return {
        art.ITENS: itens_bytes,
        art.NAMESPACE: namespace_bytes,
        art.MANIFESTO: art.serializar_manifesto(manifesto),
    }


def montar(
    repo: Path,
    ambiente: str,
    saida: Path,
    *,
    versao: Optional[str] = None,
    base_dir: Optional[Path] = None,
    base_repo: str = BASE_REPO_PADRAO,
    tar: bool = False,
    limite_bytes: int = art.LIMITE_BYTES,
    arvore: Optional[Path] = None,
) -> Dict[str, Any]:
    """Monta e grava o artefato em `saida`. Devolve o manifesto.

    Com `arvore`, grava também a montagem no layout da base (`escrever_arvore`), para os testes
    de hook do cliente lerem o metadado montado. O artefato não muda.
    """
    with tempfile.TemporaryDirectory(prefix="metas-base-") as temporario:
        if base_dir is None:
            config = ler_config(Path(repo))
            base_raiz = obter_base(config.base, base_repo, Path(temporario))
        else:
            base_raiz = Path(base_dir)
        montagem = montar_metas(Path(repo), base_raiz, ambiente, versao=versao)
    arquivos = gerar_arquivos(montagem, limite_bytes)
    saida = Path(saida)
    saida.mkdir(parents=True, exist_ok=True)
    for nome, conteudo in arquivos.items():
        (saida / nome).write_bytes(conteudo)
    if tar:
        nome_tar = f"{montagem.config.cliente}-{montagem.versao}-{ambiente}.tar.gz"
        art.escrever_tar(saida / nome_tar, arquivos)
    if arvore is not None:
        escrever_arvore(montagem, Path(arvore))
    return json.loads(arquivos[art.MANIFESTO])

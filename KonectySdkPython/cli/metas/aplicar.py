"""`metas aplicar`: leva um artefato a um tenant pela API, sem Mongo (MBD-06, 08, 09).

1. confere o sha256 do artefato e o `ambiente` do manifesto contra `TENANT_ENV` (código 2);
2. faz o `dryRun` do lote (`hookMode: 'replace'`, o artefato traz o documento completo);
3. com plano vazio e `metadataVersion` igual, termina com `aplicados=0`, sem escrever;
4. senão envia só os documentos criados ou alterados, com `hookMode: 'replace'` e
   `namespacePatch` (`namespace.json` mais `metadataVersion`), `deleteRemoved` nunca;
5. 5xx ou falha de rede: 3 novas tentativas, depois de 5, 15 e 45 s;
6. 400: os erros vêm mapeados para o `_id` e o arquivo de origem (código 1).

O token vai só no header `Authorization` do `KonectyClient`: nunca em log nem em mensagem.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence

from ...lib.exceptions import KonectyMetaBulkError
from .artefato import Artefato, ler_artefato, sha256_documento
from .erros import AplicacaoRecusadaError, LoteRecusadoError

logger = logging.getLogger("konecty.cli.metas.aplicar")

ESPERAS_PADRAO = (5.0, 15.0, 45.0)
_INDICE_EM_DETALHE = re.compile(r"index (\d+)")

Dormir = Callable[[float], Awaitable[Any]]
LerVersao = Callable[[], Awaitable[Optional[Dict[str, Any]]]]


class VersaoIlegivelError(Exception):
    """O `metadataVersion` do tenant não pôde ser lido com esta credencial."""


@dataclass
class ResultadoAplicacao:
    aplicados: int
    criados: List[str] = field(default_factory=list)
    atualizados: List[str] = field(default_factory=list)
    versao_gravada: bool = False
    preserved_hooks: Dict[str, List[str]] = field(default_factory=dict)
    hooks_removidos: Dict[str, List[str]] = field(default_factory=dict)


# --------------------------------------------------------------------------- guardas


def conferir_artefato(artefato: Artefato, tenant_env: Optional[str]) -> None:
    """sha256 e ambiente. Falha com `AplicacaoRecusadaError` antes de qualquer chamada."""
    if not artefato.sha256_confere():
        raise AplicacaoRecusadaError("sha256 do artefato não confere com o manifesto (sha256Total)")
    documentos = artefato.manifesto.get("documentos") or {}
    divergentes = [str(i["_id"]) for i in artefato.itens if documentos.get(str(i["_id"])) != sha256_documento(i)]
    if divergentes or len(documentos) != len(artefato.itens):
        raise AplicacaoRecusadaError(
            f"sha256 por documento não confere com o manifesto: {', '.join(divergentes) or 'contagem diferente'}"
        )
    if not tenant_env:
        raise AplicacaoRecusadaError("TENANT_ENV não definido: o ambiente do tenant é obrigatório")
    ambiente = artefato.manifesto.get("ambiente")
    if ambiente != tenant_env:
        raise AplicacaoRecusadaError(f"artefato de ambiente '{ambiente}' recusado no tenant de ambiente '{tenant_env}'")


# --------------------------------------------------------------------------- chamadas


def _reprovavel(erro: KonectyMetaBulkError) -> bool:
    return erro.status == 0 or erro.status >= 500


async def chamar_com_retry(
    chamada: Callable[[], Awaitable[Dict[str, Any]]],
    descricao: str,
    esperas: Sequence[float],
    dormir: Dormir,
) -> Dict[str, Any]:
    """Tenta de novo em 5xx ou falha de rede, uma vez por item de `esperas`."""
    tentativas = len(esperas) + 1
    for numero in range(1, tentativas + 1):
        try:
            return await chamada()
        except KonectyMetaBulkError as erro:
            if not _reprovavel(erro):
                raise
            situacao = "sem resposta" if erro.status == 0 else f"HTTP {erro.status}"
            if numero == tentativas:
                raise LoteRecusadoError(
                    f"{descricao}: {situacao} depois de {tentativas} tentativas; nada foi gravado"
                ) from erro
            espera = esperas[numero - 1]
            logger.warning("%s: %s; nova tentativa em %ss (%d/%d)", descricao, situacao, espera, numero, tentativas)
            await dormir(espera)
    raise AssertionError("inalcançável")


def erro_do_lote(erro: KonectyMetaBulkError, enviados: List[str], origens: Dict[str, List[str]]) -> LoteRecusadoError:
    """O 400 do lote com cada erro apontando o `_id` e o arquivo de origem. Lista completa."""
    linhas: List[str] = []
    for item in erro.errors:
        if not isinstance(item, dict):
            linhas.append(str(item))
            continue
        indice = item.get("index")
        caminho = item.get("path", "")
        if not isinstance(indice, int):
            detalhe = str(item.get("details", ""))
            achado = _INDICE_EM_DETALHE.search(detalhe)
            indice = int(achado.group(1)) if achado else None
            if not caminho and "path:" in detalhe:
                caminho = detalhe.split("path:", 1)[1].strip()
        if isinstance(indice, int) and 0 <= indice < len(enviados):
            meta_id = enviados[indice]
            origem = " + ".join(origens.get(meta_id) or ["?"])
            linhas.append(f"{meta_id} ({origem}): {caminho} {item.get('message', '')}".strip())
        else:
            linhas.append(f"{caminho} {item.get('message', '')}".strip())
    detalhe = "; ".join(linhas) or f"HTTP {erro.status}"
    return LoteRecusadoError(f"o Konecty recusou o lote de metas (HTTP {erro.status}): {detalhe}")


# --------------------------------------------------------------------------- versão


def _procurar_versao(resposta: Any) -> Optional[Dict[str, Any]]:
    candidatos = [resposta]
    if isinstance(resposta, dict):
        dados = resposta.get("data")
        candidatos += dados if isinstance(dados, list) else [dados]
    for candidato in candidatos:
        if isinstance(candidato, dict) and isinstance(candidato.get("metadataVersion"), dict):
            return candidato["metadataVersion"]
    return None


def leitor_de_versao(client: Any) -> LerVersao:
    """Lê `metadataVersion` do Namespace por `GET /api/admin/meta/Namespace`.

    Devolve `None` quando o tenant não tem a chave; levanta `VersaoIlegivelError` quando a rota
    recusa a credencial (o core não expõe essa leitura a PAT de service account hoje).
    """

    async def ler() -> Optional[Dict[str, Any]]:
        try:
            resposta = await client.read_meta("Namespace")
        except Exception as erro:  # noqa: BLE001 - qualquer recusa vira "não sei"
            raise VersaoIlegivelError(type(erro).__name__) from None
        return _procurar_versao(resposta)

    return ler


async def quem_aplica(client: Any) -> str:
    try:
        info = await client.info()
    except Exception:  # noqa: BLE001
        return "desconhecido"
    usuario = info.get("user") if isinstance(info, dict) else None
    return str(usuario.get("_id")) if isinstance(usuario, dict) and usuario.get("_id") else "desconhecido"


def versao_do_artefato(artefato: Artefato, aplicado_por: str, origem: Optional[str], agora: datetime) -> Dict[str, Any]:
    m = artefato.manifesto
    versao: Dict[str, Any] = {
        "cliente": m.get("cliente"),
        "versaoCliente": m.get("versaoCliente"),
        "base": m.get("base"),
        "sha256": m.get("sha256Total"),
        "ambiente": m.get("ambiente"),
        "aplicadoEm": agora.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "aplicadoPor": aplicado_por,
    }
    if origem:
        versao["origem"] = origem
    return versao


def _mesma_versao(atual: Optional[Dict[str, Any]], artefato: Artefato) -> bool:
    return (
        isinstance(atual, dict)
        and atual.get("sha256") == artefato.manifesto.get("sha256Total")
        and atual.get("ambiente") == artefato.manifesto.get("ambiente")
    )


# --------------------------------------------------------------------------- aplicar


async def aplicar(
    pasta: Path,
    client: Any,
    *,
    tenant_env: Optional[str],
    origem: Optional[str] = None,
    ler_versao: Optional[LerVersao] = None,
    esperas: Sequence[float] = ESPERAS_PADRAO,
    dormir: Optional[Dormir] = None,
    agora: Optional[Callable[[], datetime]] = None,
) -> ResultadoAplicacao:
    dormir = dormir or asyncio.sleep
    artefato = ler_artefato(Path(pasta))
    conferir_artefato(artefato, tenant_env)
    origens: Dict[str, List[str]] = artefato.manifesto.get("origens") or {}
    todos = [str(item["_id"]) for item in artefato.itens]
    por_id = artefato.por_id

    try:
        simulado = await chamar_com_retry(
            lambda: client.apply_meta_bulk(artefato.itens, dry_run=True, hook_mode="replace"),
            "dryRun do lote",
            esperas,
            dormir,
        )
    except KonectyMetaBulkError as erro:
        raise erro_do_lote(erro, todos, origens) from None

    plano = simulado.get("plan") or {}
    criados = sorted(plano.get("created") or [])
    atualizados = sorted(str(u.get("_id")) for u in plano.get("updated") or [])
    hooks_removidos = plano.get("hooksRemoved") or {}
    logger.info(
        "dryRun: %d criados, %d alterados, %s iguais", len(criados), len(atualizados), plano.get("unchanged", "?")
    )
    if hooks_removidos:
        logger.warning("dryRun: hooks que o artefato remove: %s", hooks_removidos)

    try:
        atual = await (ler_versao or leitor_de_versao(client))()
        legivel = True
    except VersaoIlegivelError as erro:
        atual, legivel = None, False
        logger.warning("metadataVersion do tenant ilegível com esta credencial (%s)", erro)

    mudados = criados + atualizados
    resultado = ResultadoAplicacao(
        aplicados=0, criados=criados, atualizados=atualizados, hooks_removidos=hooks_removidos
    )
    if not mudados and (_mesma_versao(atual, artefato) or not legivel):
        if not legivel:
            logger.warning("plano vazio e versão não conferida: nada gravado, metadataVersion não atualizado")
        logger.info("aplicados=0: o tenant já está no artefato %s", artefato.manifesto.get("sha256Total"))
        return resultado

    # O lote recusa `items` vazio: só a versão mudou, então vai um documento igual (no-op).
    enviados = sorted(mudados) or [todos[0]]
    momento = (agora or (lambda: datetime.now(timezone.utc)))()
    patch_namespace = {
        **artefato.namespace,
        "metadataVersion": versao_do_artefato(artefato, await quem_aplica(client), origem, momento),
    }
    try:
        resposta = await chamar_com_retry(
            lambda: client.apply_meta_bulk(
                [por_id[meta_id] for meta_id in enviados],
                hook_mode="replace",
                namespace_patch=patch_namespace,
            ),
            "aplicação do lote",
            esperas,
            dormir,
        )
    except KonectyMetaBulkError as erro:
        raise erro_do_lote(erro, enviados, origens) from None

    resultado.aplicados = len(mudados)
    resultado.versao_gravada = True
    resultado.preserved_hooks = resposta.get("preservedHooks") or {}
    for aviso in resposta.get("warnings") or []:
        logger.warning("Konecty: %s", aviso)
    if resultado.preserved_hooks:
        logger.info("preservedHooks: %s", resultado.preserved_hooks)
    logger.info(
        "aplicados=%d (criados=%d, alterados=%d), metadataVersion=%s",
        resultado.aplicados,
        len(criados),
        len(atualizados),
        artefato.manifesto.get("sha256Total"),
    )
    return resultado

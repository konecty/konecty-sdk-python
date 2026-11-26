"""`metas aplicar`: leva um artefato a um tenant pela API, sem Mongo (MBD-06, 08, 09).

1. confere o sha256 do artefato e o `ambiente` do manifesto contra `TENANT_ENV` (código 2);
2. faz o `dryRun` do lote (`hookMode: 'replace'`, o artefato traz o documento completo) com o
   `namespacePatch` de identidade (`namespace.json` mais `metadataVersion`). O PAT não lê o
   Namespace: quem diz se ele muda é o `plan.namespace.keys` do core (AD-MBD-003);
3. sem item a criar ou alterar e com `plan.namespace.keys` vazio, termina com `aplicados=0`;
4. senão envia só os documentos criados ou alterados, com `hookMode: 'replace'` e o
   `namespacePatch` mais `metadataAplicacao` (data, quem aplicou, commit), `deleteRemoved` nunca;
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


async def quem_aplica(client: Any) -> str:
    try:
        info = await client.info()
    except Exception:  # noqa: BLE001
        return "desconhecido"
    usuario = info.get("user") if isinstance(info, dict) else None
    return str(usuario.get("_id")) if isinstance(usuario, dict) and usuario.get("_id") else "desconhecido"


def versao_do_artefato(artefato: Artefato) -> Dict[str, Any]:
    """A identidade do artefato. Estável: aplicar o mesmo artefato de novo dá o mesmo valor."""
    m = artefato.manifesto
    return {
        "cliente": m.get("cliente"),
        "versaoCliente": m.get("versaoCliente"),
        "base": m.get("base"),
        "sha256": m.get("sha256Total"),
        "ambiente": m.get("ambiente"),
    }


def aplicacao(aplicado_por: str, origem: Optional[str], agora: datetime) -> Dict[str, Any]:
    """Quando, por quem e de qual commit. Fica fora do `metadataVersion` para não sujar o dryRun."""
    dados: Dict[str, Any] = {
        "aplicadoEm": agora.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "aplicadoPor": aplicado_por,
    }
    if origem:
        dados["origem"] = origem
    return dados


# --------------------------------------------------------------------------- aplicar


async def aplicar(
    pasta: Path,
    client: Any,
    *,
    tenant_env: Optional[str],
    origem: Optional[str] = None,
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
    patch_identidade = {**artefato.namespace, "metadataVersion": versao_do_artefato(artefato)}

    try:
        simulado = await chamar_com_retry(
            lambda: client.apply_meta_bulk(
                artefato.itens, dry_run=True, hook_mode="replace", namespace_patch=patch_identidade
            ),
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

    chaves_namespace = sorted((plano.get("namespace") or {}).get("keys") or [])
    if chaves_namespace:
        logger.info("dryRun: Namespace muda em %s", ", ".join(chaves_namespace))

    mudados = criados + atualizados
    resultado = ResultadoAplicacao(
        aplicados=0, criados=criados, atualizados=atualizados, hooks_removidos=hooks_removidos
    )
    if not mudados and not chaves_namespace:
        logger.info("aplicados=0: o tenant já está no artefato %s", artefato.manifesto.get("sha256Total"))
        return resultado

    # O lote recusa `items` vazio: só a versão mudou, então vai um documento igual (no-op).
    enviados = sorted(mudados) or [todos[0]]
    momento = (agora or (lambda: datetime.now(timezone.utc)))()
    patch_namespace = {
        **patch_identidade,
        "metadataAplicacao": aplicacao(await quem_aplica(client), origem, momento),
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

"""`metas deriva`: o quanto o tenant diverge do artefato aplicado (MBD-14). Nunca escreve.

Faz só o `dryRun` do lote (`hookMode: 'replace'`, como o `aplicar`) e publica:

- a métrica como linha de log no formato de exposição do Prometheus, que o Loki transforma em
  métrica: `konecty_metadata_drift_documents{tenant="<tenant>"} <n>`;
- a lista por documento e chave (documento ausente no tenant conta como divergente).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from ...lib.exceptions import KonectyMetaBulkError
from .aplicar import ESPERAS_PADRAO, Dormir, chamar_com_retry, conferir_artefato, erro_do_lote
from .artefato import ler_artefato

logger = logging.getLogger("konecty.cli.metas.deriva")

METRICA = "konecty_metadata_drift_documents"


@dataclass
class Deriva:
    tenant: str
    ausentes: List[str] = field(default_factory=list)
    divergentes: Dict[str, List[str]] = field(default_factory=dict)

    @property
    def documentos(self) -> int:
        return len(self.ausentes) + len(self.divergentes)

    def linha_metrica(self) -> str:
        rotulo = self.tenant.replace("\\", "\\\\").replace('"', '\\"')
        return f'{METRICA}{{tenant="{rotulo}"}} {self.documentos}'

    def linhas(self) -> List[str]:
        saida = [self.linha_metrica()]
        saida += [f"ausente no tenant: {meta_id}" for meta_id in self.ausentes]
        saida += [f"diverge: {meta_id}: {', '.join(chaves)}" for meta_id, chaves in self.divergentes.items()]
        return saida


async def deriva(
    pasta: Path,
    client: Any,
    *,
    tenant_env: Optional[str],
    tenant: Optional[str] = None,
    esperas: Sequence[float] = ESPERAS_PADRAO,
    dormir: Optional[Dormir] = None,
) -> Deriva:
    artefato = ler_artefato(Path(pasta))
    conferir_artefato(artefato, tenant_env)
    nome = tenant or f"{artefato.manifesto.get('cliente')}-{artefato.manifesto.get('ambiente')}"
    todos = [str(item["_id"]) for item in artefato.itens]
    try:
        resposta = await chamar_com_retry(
            lambda: client.apply_meta_bulk(artefato.itens, dry_run=True, hook_mode="replace"),
            "dryRun da deriva",
            esperas,
            dormir or asyncio.sleep,
        )
    except KonectyMetaBulkError as erro:
        raise erro_do_lote(erro, todos, artefato.manifesto.get("origens") or {}) from None
    plano = resposta.get("plan") or {}
    resultado = Deriva(tenant=nome, ausentes=sorted(plano.get("created") or []))
    for atualizado in sorted(plano.get("updated") or [], key=lambda u: str(u.get("_id"))):
        resultado.divergentes[str(atualizado.get("_id"))] = list(atualizado.get("keys") or [])
    for linha in resultado.linhas():
        logger.info("%s", linha)
    return resultado

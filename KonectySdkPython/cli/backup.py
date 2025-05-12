"""Script para fazer backup dos documentos do MongoDB."""

import asyncio
import json
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

import click
from pymongo import MongoClient
from rich.console import Console
from rich.progress import Progress

console = Console()


@click.command(name="backup")
@click.option("--host", default="localhost", help="Host do MongoDB")
@click.option("--port", type=int, default=27017, help="Porta do MongoDB")
@click.option("--database", required=True, help="Nome do banco de dados")
@click.option("--output", default="backups", help="Diretório para salvar o backup")
@click.option("--username", help="Usuário do MongoDB")
@click.option("--password", help="Senha do MongoDB")
@click.option("--replicaset", help="Nome do ReplicaSet do MongoDB (ex: rs0)")
@click.option("--version", help="Rótulo de versão para o arquivo de backup")
@click.option("--mongo-url", help="URL do MongoDB")
def backup_command(
    host: str,
    port: int,
    database: str,
    output: str,
    username: Optional[str],
    password: Optional[str],
    replicaset: Optional[str],
    version: Optional[str],
    mongo_url: Optional[str],
) -> None:
    """Gera backup dos documentos do MongoDB."""
    asyncio.run(
        _backup_command(
            host=host,
            port=port,
            database=database,
            output=output,
            username=username,
            password=password,
            replicaset=replicaset,
            version=version,
            mongo_url=mongo_url,
        )
    )


async def _backup_command(
    host: str,
    port: int,
    database: str,
    output: str,
    username: Optional[str],
    password: Optional[str],
    replicaset: Optional[str],
    version: Optional[str],
    mongo_url: Optional[str],
) -> None:
    """Internal async implementation of backup command."""
    output_dir = Path(output).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    # Gera nome do arquivo de backup
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    version_label = f"_{version}" if version else ""
    backup_file = output_dir / f"backup_{timestamp}{version_label}.tar.gz"

    uri = mongo_url

    if not uri:
        uri_params = []
        if replicaset:
            uri_params.extend(
                [
                    f"replicaSet={replicaset}",
                    "directConnection=false",
                    "retryWrites=true",
                    "w=majority",
                ]
            )

        uri_suffix = f"?{'&'.join(uri_params)}" if uri_params else ""

        if username and password:
            uri = f"mongodb://{username}:{password}@{host}:{port}/admin{uri_suffix}"
        else:
            uri = f"mongodb://{host}:{port}{uri_suffix}"

    client = MongoClient(
        uri,
        serverSelectionTimeoutMS=30000,
        connectTimeoutMS=20000,
        socketTimeoutMS=20000,
        maxPoolSize=1,
    )
    db = client[database]
    collection = db["MetaObjects"]

    # Cria diretório temporário
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Busca todos os documentos
        documents = list(collection.find({"type": {"$in": ["composite", "document"]}}))

        with Progress() as progress:
            task = progress.add_task("[cyan]Gerando backup...", total=len(documents))

            # Processa cada documento
            for doc in documents:
                doc_path = temp_path / doc["name"]
                doc_path.mkdir(parents=True, exist_ok=True)

                # Salva documento principal
                doc_file = doc_path / "document.json"
                doc_file.write_text(json.dumps(doc, indent=2))

                # Busca documentos relacionados
                related = list(collection.find({"document": doc["name"]}))

                for rel in related:
                    rel_type = rel["type"]
                    type_path = doc_path / rel_type
                    type_path.mkdir(exist_ok=True)

                    rel_file = type_path / f"{rel['name']}.json"
                    rel_file.write_text(json.dumps(rel, indent=2))

                progress.update(task, advance=1)

        # Cria arquivo tar.gz
        with tarfile.open(backup_file, "w:gz") as tar:
            tar.add(temp_dir, arcname="metadata")

    client.close()
    console.print(
        f"[green]Backup concluído com sucesso:[/green] [cyan]{backup_file}[/cyan]"
    )


def main():
    """Entry point for the CLI."""
    import asyncio
    import sys

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    backup_command()


if __name__ == "__main__":
    main()

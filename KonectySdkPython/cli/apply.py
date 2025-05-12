# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "click",
#     "inquirer",
#     "pymongo",
#     "rich",
# ]
# ///
"""Script para aplicar alterações locais ao MongoDB."""

import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Set, Tuple, TypedDict, cast

import click
import inquirer
from pymongo import MongoClient
from rich.console import Console
from rich.progress import Progress
from rich.table import Table


class DocFiles(TypedDict):
    document: List[Path]
    view: List[Path]
    list: List[Path]
    pivot: List[Path]
    access: List[Path]
    hook: List[Path]


DocType = Literal["document", "view", "list", "pivot", "access", "hook"]
MetaType = Literal["view", "list", "pivot", "access"]


console = Console()


def load_json_file(file_path: Path) -> dict:
    """Carrega um arquivo JSON."""
    try:
        return json.loads(file_path.read_text())
    except Exception as error:
        console.print(f"[red]Erro ao ler arquivo {file_path}[/red]: {str(error)}")
        return {}


def find_metadata_files(metadata_dir: Path) -> Dict[str, DocFiles]:
    """Encontra todos os arquivos de metadados no diretório."""
    result: Dict[str, DocFiles] = {}

    for doc_dir in metadata_dir.iterdir():
        if not doc_dir.is_dir():
            continue

        doc_files: DocFiles = {
            "document": [],
            "view": [],
            "list": [],
            "pivot": [],
            "access": [],
            "hook": [],
        }

        # Documento principal
        doc_file = doc_dir / "document.json"
        if doc_file.exists():
            doc_files["document"].append(doc_file)

        # Views, lists, pivots e access
        for type_name in ("view", "list", "pivot", "access"):
            type_name_key = cast(MetaType, type_name)
            type_dir = doc_dir / type_name
            if type_dir.exists():
                doc_files[type_name_key].extend(sorted(type_dir.glob("*.json")))

        # Hooks
        hook_dir = doc_dir / "hook"
        if hook_dir.exists():
            doc_files["hook"].extend(sorted(hook_dir.glob("*.*")))

        if any(files for files in doc_files.values()):
            result[doc_dir.name] = doc_files

    return result


def is_equal_documents(doc1: dict, doc2: dict) -> bool:
    """Compara dois documentos ignorando campos específicos."""
    # Campos para ignorar na comparação
    ignore_fields = ["_id", "_createdAt", "_updatedAt", "_createdBy", "_updatedBy"]

    # Cria cópias para não modificar os originais
    doc1_copy = doc1.copy()
    doc2_copy = doc2.copy()

    # Remove campos ignorados
    for field in ignore_fields:
        doc1_copy.pop(field, None)
        doc2_copy.pop(field, None)

    return doc1_copy == doc2_copy


async def apply_document(
    collection,
    doc_name: str,
    doc_files: DocFiles,
    dry_run: bool = False,
) -> Tuple[List[str], List[str], List[str]]:
    """Aplica as alterações de um documento."""
    applied = []
    errors = []
    skipped = []

    # Documento principal
    if doc_files["document"]:
        doc_data = load_json_file(doc_files["document"][0])
        if doc_data:
            existing_doc = collection.find_one(
                {"_id": doc_data["_id"], "type": {"$in": ["composite", "document"]}}
            )

            if existing_doc and is_equal_documents(doc_data, existing_doc):
                skipped.append(f"⚡ {doc_name} (document) [identical]")
            else:
                if not dry_run:
                    try:
                        collection.update_one(
                            {
                                "_id": doc_data["_id"],
                                "type": {"$in": ["composite", "document"]},
                            },
                            {"$set": doc_data},
                            upsert=True,
                        )
                        applied.append(f"✓ {doc_name} (document)")
                    except Exception as error:
                        print(doc_data["_id"], f"{doc_name} (document)")
                        print(error)
                        errors.append(f"✗ {doc_name} (document): {str(error)}")
                else:
                    applied.append(f"✓ {doc_name} (document) [dry-run]")

    # Views, lists, pivots e access
    existing_data: dict[str, Any] | None = None
    data: Any

    for type_name in ("view", "list", "pivot", "access"):
        type_name_key = cast(MetaType, type_name)
        for file_path in doc_files[type_name_key]:
            data = load_json_file(file_path)
            if data:
                existing_data = collection.find_one(
                    {"name": data["name"], "type": type_name, "document": doc_name}
                )

                if existing_data and is_equal_documents(data, existing_data):
                    skipped.append(
                        f"⚡ {doc_name}/{type_name}/{data['name']} [identical]"
                    )
                else:
                    if not dry_run:
                        try:
                            collection.update_one(
                                {
                                    "name": data["name"],
                                    "type": type_name,
                                    "document": doc_name,
                                },
                                {"$set": data},
                                upsert=True,
                            )
                            applied.append(f"✓ {doc_name}/{type_name}/{data['name']}")
                        except Exception as error:
                            print(
                                data["_id"],
                                data["name"],
                                f"{doc_name}/{type_name}/{data['name']}",
                            )
                            print(error)
                            errors.append(
                                f"✗ {doc_name}/{type_name}/{data['name']}: {str(error)}"
                            )
                    else:
                        applied.append(
                            f"✓ {doc_name}/{type_name}/{data['name']} [dry-run]"
                        )

    # Hooks
    for file_path in doc_files["hook"]:
        data = file_path.read_text()
        if data:
            existing_data = collection.find_one(
                {"name": doc_name, "type": {"$in": ["composite", "document"]}}
            )
            hook_name = file_path.stem
            if existing_data:
                if existing_data.get(hook_name, None) == data:
                    skipped.append(f"⚡ {doc_name}/{hook_name} [identical]")
                else:
                    if not dry_run:
                        try:
                            collection.update_one(
                                {
                                    "name": doc_name,
                                    "type": {"$in": ["composite", "document"]},
                                },
                                {"$set": {hook_name: data}},
                            )
                            applied.append(f"✓ {doc_name}/{hook_name}")
                        except Exception as error:
                            errors.append(f"✗ {doc_name}/{hook_name}: {str(error)}")
                    else:
                        applied.append(f"✓ {doc_name}/{hook_name} [dry-run]")

    return applied, errors, skipped


async def prune_documents(
    collection,
    local_docs: Set[str],
    dry_run: bool = False,
) -> Tuple[List[str], List[str]]:
    """Remove documentos que não existem localmente."""
    pruned = []
    errors = []

    # Encontra documentos no banco que não existem localmente
    remote_docs = set(
        doc["name"]
        for doc in collection.find(
            {"type": {"$in": ["composite", "document"]}, "name": {"$ne": "_id"}},
            {"name": 1},
        )
    )

    to_remove = remote_docs - local_docs

    for doc_name in to_remove:
        if not dry_run:
            try:
                # Remove documento principal
                collection.delete_one(
                    {"name": doc_name, "type": {"$in": ["composite", "document"]}}
                )
                # Remove documentos relacionados
                collection.delete_many({"document": doc_name})
                pruned.append(f"✓ {doc_name}")
            except Exception as error:
                errors.append(f"✗ {doc_name}: {str(error)}")
        else:
            pruned.append(f"✓ {doc_name} [dry-run]")

    return pruned, errors


async def apply_namespace(
    collection,
    metadata_dir: Path,
    dry_run: bool = False,
) -> Tuple[List[str], List[str], List[str]]:
    """Aplica as alterações do Namespace."""
    applied = []
    errors = []
    skipped = []

    base_namespace = {
        "_id": "Namespace",
        "name": "konecty",
        "type": "namespace",
        "ns": "konecty",
        "active": True,
    }

    namespace_file = metadata_dir / "Namespace.json"
    if not namespace_file.exists():
        namespace_data = base_namespace
    else:
        namespace_data = load_json_file(namespace_file)
        if not namespace_data:
            return [], ["✗ Namespace.json: Arquivo vazio ou inválido"], []

    existing_namespace = collection.find_one({"_id": "Namespace"})

    def compare_namespace(ns1: dict, ns2: dict) -> bool:
        """Compara dois namespaces ignorando _id e name."""
        ns1_copy = ns1.copy()
        ns2_copy = ns2.copy()

        ignore_fields = ["_id", "name", "ns"]
        for field in ignore_fields:
            ns1_copy.pop(field, None)
            ns2_copy.pop(field, None)

        return ns1_copy == ns2_copy

    if existing_namespace and compare_namespace(namespace_data, existing_namespace):
        skipped.append("⚡ Namespace.json [identical]")
    else:
        if not dry_run:
            try:
                if existing_namespace:
                    collection.update_one(
                        {"_id": "Namespace"}, {"$set": namespace_data}
                    )
                else:
                    collection.insert_one({**base_namespace, **namespace_data})
                applied.append("✓ Namespace.json")
            except Exception as error:
                errors.append(f"✗ Namespace.json: {str(error)}")
        else:
            applied.append("✓ Namespace.json [dry-run]")

    return applied, errors, skipped


@click.command(name="apply")
@click.option("--metadata-dir", default="metadata", help="Diretório com os metadados")
@click.option("--host", default="localhost", help="Host do MongoDB")
@click.option("--port", type=int, default=27017, help="Porta do MongoDB")
@click.option("--database", default="default", help="Nome do banco de dados")
@click.option("--username", help="Usuário do MongoDB")
@click.option("--password", help="Senha do MongoDB")
@click.option("--replicaset", help="Nome do ReplicaSet do MongoDB (ex: rs0)")
@click.option("--document", help="Nome do documento para aplicar")
@click.option(
    "--prune", is_flag=True, help="Remove documentos que não existem localmente"
)
@click.option("--dry-run", is_flag=True, help="Simula as alterações sem aplicá-las")
@click.option("--direct-connection", is_flag=True, help="Usa conexão direta ao MongoDB")
@click.option(
    "--retry-writes",
    is_flag=True,
    default=True,
    help="Tenta reescrever em caso de falha",
)
@click.option("--w", default="majority", help="Nível de escrita do MongoDB")
@click.option("--mongo-url", help="URL do MongoDB")
def apply_command(
    metadata_dir: str,
    host: str,
    port: int,
    database: str,
    username: Optional[str],
    password: Optional[str],
    replicaset: Optional[str],
    document: Optional[str],
    prune: bool,
    dry_run: bool,
    direct_connection: bool,
    retry_writes: bool,
    w: str,
    mongo_url: Optional[str],
) -> None:
    """Aplica alterações locais ao MongoDB."""
    asyncio.run(
        _apply_command(
            metadata_dir=metadata_dir,
            host=host,
            port=port,
            database=database,
            username=username,
            password=password,
            replicaset=replicaset,
            document=document,
            prune=prune,
            dry_run=dry_run,
            direct_connection=direct_connection,
            retry_writes=retry_writes,
            w=w,
            mongo_url=mongo_url,
        )
    )


async def _apply_command(
    metadata_dir: str,
    host: str,
    port: int,
    database: str,
    username: Optional[str],
    password: Optional[str],
    replicaset: Optional[str],
    document: Optional[str],
    prune: bool,
    dry_run: bool,
    direct_connection: bool,
    retry_writes: bool,
    w: str,
    mongo_url: Optional[str],
) -> None:
    """Internal async implementation of apply command."""
    metadata_path = Path(metadata_dir).resolve()
    if not metadata_path.exists():
        console.print(f"[red]Diretório {metadata_dir} não encontrado[/red]")
        return

    uri = mongo_url

    if not uri:
        uri_params = []
        if replicaset:
            uri_params.extend(
                [
                    f"replicaSet={replicaset}",
                    f"directConnection={'true' if direct_connection else 'false'}",
                    f"retryWrites={'true' if retry_writes else 'false'}",
                    f"w={w}",
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

    # Se o documento for Namespace, aplica apenas o Namespace
    if document == "Namespace":
        namespace_applied, namespace_errors, namespace_skipped = await apply_namespace(
            collection, metadata_path, dry_run
        )
        table = Table(title="Resultados da Aplicação")
        table.add_column("Documento")
        table.add_column("Status")
        table.add_column("Pulados")
        table.add_column("Erros")
        if namespace_applied or namespace_errors or namespace_skipped:
            table.add_row(
                "@Namespace",
                "\n".join(namespace_applied),
                "\n".join(namespace_skipped),
                "\n".join(namespace_errors),
            )
        client.close()
        console.print(table)
        return

    # Encontra todos os arquivos de metadados
    all_files = find_metadata_files(metadata_path)

    if not all_files:
        console.print("[yellow]Nenhum arquivo de metadados encontrado[/yellow]")
        return

    # Se nenhum documento específico foi fornecido, pergunta ao usuário
    if document is None:
        choices = [
            {"name": "Todos", "value": "all"},
            *[{"name": name, "value": name} for name in sorted(all_files.keys())],
        ]

        questions = [
            inquirer.List(
                "document",
                message="Qual documento você deseja aplicar?",
                choices=[choice["name"] for choice in choices],
            )
        ]

        answers = inquirer.prompt(questions)
        if answers is None:
            console.print("[red]Operação cancelada pelo usuário[/red]")
            return

        document = "all" if answers["document"] == "Todos" else answers["document"]

    # Determina quais documentos processar
    docs_to_process = list(all_files.keys()) if document == "all" else [document]

    if document != "all" and document not in all_files:
        console.print(f"[red]Documento {document} não encontrado[/red]")
        return

    # Aplica o Namespace primeiro
    namespace_applied, namespace_errors, namespace_skipped = await apply_namespace(
        collection, metadata_path, dry_run
    )

    table = Table(title="Resultados da Aplicação")
    table.add_column("Documento")
    table.add_column("Status")
    table.add_column("Pulados")
    table.add_column("Erros")

    if namespace_applied or namespace_errors or namespace_skipped:
        table.add_row(
            "@Namespace",
            "\n".join(namespace_applied),
            "\n".join(namespace_skipped),
            "\n".join(namespace_errors),
        )

    with Progress() as progress:
        task = progress.add_task(
            "[cyan]Aplicando alterações...", total=len(docs_to_process)
        )

        for doc_name in docs_to_process:
            applied, errors, skipped = await apply_document(
                collection, doc_name, all_files[doc_name], dry_run
            )

            table.add_row(
                doc_name,
                "\n".join(applied),
                "\n".join(skipped),
                "\n".join(errors) if errors else "",
            )

            progress.update(task, advance=1)

    if prune:
        pruned, prune_errors = await prune_documents(
            collection, set(all_files.keys()), dry_run
        )
        if pruned or prune_errors:
            table.add_row(
                "Prune",
                "\n".join(pruned),
                "",
                "\n".join(prune_errors) if prune_errors else "",
            )

    client.close()
    console.print(table)


def main():
    """Entry point for the CLI."""
    import asyncio
    import sys

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    apply_command()


if __name__ == "__main__":
    main()

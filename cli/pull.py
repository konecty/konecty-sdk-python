"""Script para extrair dados do MongoDB e gerar arquivos JSON."""

import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, TypedDict, Union, cast

import black
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


class RelatedResults(TypedDict):
    view: List[str]
    list: List[str]
    pivot: List[str]
    access: List[str]


class MongoFilter(TypedDict, total=False):
    document: str
    type: str
    name: str
    or_conditions: List[Dict[str, str]]


class MongoCondition(TypedDict, total=False):
    type: str
    name: str


MongoQuery = Dict[str, Union[str, List[MongoCondition]]]


DocType = Literal["document", "view", "list", "pivot", "access", "hook"]
MetaType = Literal["view", "list", "pivot", "access"]


console = Console()


def format_code(name: str, code: str) -> str:
    """Formata o código JavaScript usando black."""
    try:
        return black.format_str(code, mode=black.Mode())
    except Exception as error:
        console.print(f"[red]Erro ao formatar código {name}[/red]: {str(error)}")
        return code


async def write_file(file_path: str, content: str) -> None:
    """Escreve conteúdo em um arquivo, criando diretórios se necessário."""
    try:
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    except Exception as error:
        console.print(f"[red]Erro ao escrever arquivo {file_path}[/red]: {str(error)}")


@click.command(name="pull")
@click.option("--host", default="localhost", help="Host do MongoDB")
@click.option("--port", type=int, default=27017, help="Porta do MongoDB")
@click.option("--database", default="default", help="Nome do banco de dados")
@click.option("--output", default="metadata", help="Diretório para salvar os metadados")
@click.option("--username", help="Usuário do MongoDB")
@click.option("--password", help="Senha do MongoDB")
@click.option("--replicaset", help="Nome do ReplicaSet do MongoDB (ex: rs0)")
@click.option("--document", help="Nome do documento para baixar")
@click.option("--view", help="Nome da view específica para extrair")
@click.option("--list", "list_param", help="Nome da lista específica para extrair")
@click.option("--pivot", help="Nome do pivot específico para extrair")
@click.option("--access", help="Nome do access específica para extrair")
@click.option("--hook", help="Nome do hook específico para extrair")
@click.option("--mongo-url", help="URL do MongoDB")
@click.option(
    "--all",
    "extract_all",
    is_flag=True,
    help="Extrair todas as collections sem perguntar",
)
def pull_command(
    host: str,
    port: int,
    database: str,
    output: str,
    username: Optional[str],
    password: Optional[str],
    replicaset: Optional[str],
    document: Optional[str],
    view: Optional[str],
    list_param: Optional[str],
    pivot: Optional[str],
    access: Optional[str],
    hook: Optional[str],
    extract_all: bool,
    mongo_url: Optional[str],
) -> None:
    """Baixa metadados do MongoDB."""
    asyncio.run(
        _pull_command(
            host=host,
            port=port,
            database=database,
            output=output,
            username=username,
            password=password,
            replicaset=replicaset,
            document=document,
            view=view,
            list_param=list_param,
            pivot=pivot,
            access=access,
            hook=hook,
            extract_all=extract_all,
            mongo_url=mongo_url,
        )
    )


async def _pull_command(
    host: str,
    port: int,
    database: str,
    output: str,
    username: Optional[str],
    password: Optional[str],
    replicaset: Optional[str],
    document: Optional[str],
    view: Optional[str],
    list_param: Optional[str],
    pivot: Optional[str],
    access: Optional[str],
    hook: Optional[str],
    mongo_url: Optional[str],
    extract_all: bool,
) -> None:
    """Internal async implementation of pull command."""
    output_dir = Path(output).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

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

    table = Table(title="Resultados da Extração")
    table.add_column("Documento")
    table.add_column("Hook")
    table.add_column("View")
    table.add_column("List")
    table.add_column("Pivot")
    table.add_column("Access")

    if document is None and not extract_all:
        document_names = list(
            collection.find(
                {"type": {"$in": ["composite", "document"]}}, {"name": 1}
            ).sort("name", 1)
        )
        if not document_names:
            console.print("[red]Nenhum documento encontrado.[/red]")
            return

        document_names = [doc["name"] for doc in document_names]
        document_names.append("Todos")

        questions = [
            inquirer.List(
                "document",
                message="Selecione o documento para extrair",
                choices=document_names,
            )
        ]
        answers = inquirer.prompt(questions)
        if not answers:
            return
        document = "all" if answers["document"] == "Todos" else answers["document"]
    elif extract_all:
        document = "all"

    filter_query: Dict[str, Any] = {"type": {"$in": ["composite", "document"]}}
    if document != "all":
        filter_query["name"] = document

    documents = list(collection.find(filter_query).sort("name", 1))

    with Progress() as progress:
        task = progress.add_task("[cyan]Extraindo metadados...", total=len(documents))

        for doc in documents:
            doc_path = output_dir / doc["name"]
            doc_path.mkdir(parents=True, exist_ok=True)

            # Processando hooks
            hook_results = []
            if "validationData" in doc:
                await write_file(
                    str(doc_path / "hook" / "validationData.json"),
                    json.dumps(doc["validationData"], indent=2),
                )
                hook_results.append("✓ validationData")

            for script_type in [
                "scriptBeforeValidation",
                "validationScript",
                "scriptAfterSave",
            ]:
                if script_type in doc:
                    formatted = format_code(f"{script_type}.js", doc[script_type])
                    await write_file(
                        str(doc_path / "hook" / f"{script_type}.js"), formatted
                    )
                    hook_results.append(f"✓ {script_type}")

            # Processando views, lists, pivots e access
            related_results: RelatedResults = {
                "view": [],
                "list": [],
                "pivot": [],
                "access": [],
            }
            for type_name, param in [
                ("view", extract_all or view),
                ("list", extract_all or list_param),
                ("pivot", extract_all or pivot),
                ("access", extract_all or access),
            ]:
                if param is not None:
                    condition = {"type": type_name}
                    if not extract_all:
                        condition["name"] = param
                    related_metas = list(collection.find(condition).sort("_id", 1))
                    for meta in related_metas:
                        meta_type = cast(MetaType, meta["type"])
                        if meta_type in ("view", "list", "pivot", "access"):
                            await write_file(
                                str(doc_path / meta_type / f"{meta['name']}.json"),
                                json.dumps(meta, indent=2),
                            )
                            related_results[meta_type].append(f"✓ {meta['name']}")

            table.add_row(
                doc["name"],
                "\n".join(hook_results),
                "\n".join(related_results["view"]),
                "\n".join(related_results["list"]),
                "\n".join(related_results["pivot"]),
                "\n".join(related_results["access"]),
            )

            progress.update(task, advance=1)

    console.print(table)
    client.close()


def main():
    """Entry point for the CLI."""
    import asyncio
    import sys

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    pull_command()


if __name__ == "__main__":
    main()

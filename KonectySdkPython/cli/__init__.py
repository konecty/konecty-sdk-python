"""CLI tools for Konecty metadata management."""

import click
from rich.console import Console

console = Console()


@click.group()
def cli():
    """Konecty CLI tools for metadata management."""
    pass


# Import commands after cli group is defined to avoid circular imports
from .apply import apply_command
from .backup import backup_command
from .pull import pull_command

# Add commands to the group
cli.add_command(apply_command)
cli.add_command(backup_command)
cli.add_command(pull_command)


def main():
    """Entry point for the CLI."""
    import asyncio
    import sys

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    asyncio.run(cli())


if __name__ == "__main__":
    main()

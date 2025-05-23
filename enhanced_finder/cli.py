"""Command-line interface for Enhanced Finder."""

import asyncio
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Prompt, Confirm

from .config import FinderConfig
from .indexer import DocumentIndexer
from .simple_agents import SimpleSearchAgent, SimpleIndexingAgent

app = typer.Typer(help="Enhanced Finder - Intelligent file search for macOS")
console = Console()


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query"),
    max_results: int = typer.Option(10, "--max", "-m", help="Maximum number of results"),
    file_type: Optional[str] = typer.Option(None, "--type", "-t", help="Filter by file type"),
    output_format: str = typer.Option("table", "--format", "-f", help="Output format: table, json, simple")
):
    """Search for files using intelligent semantic and filename matching."""
    asyncio.run(_search_async(query, max_results, file_type, output_format))


async def _search_async(query: str, max_results: int, file_type: Optional[str], output_format: str):
    """Async search implementation."""
    config = FinderConfig()
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Initializing search...", total=None)
        
        indexer = DocumentIndexer(config)
        indexer.load_or_create_index()
        
        if indexer.index is None or indexer.index.ntotal == 0:
            console.print("[red]No indexed files found. Please run 'enhanced-finder index' first.[/red]")
            return
        
        progress.update(task, description="Searching files...")
        
        search_agent = SimpleSearchAgent(config, indexer)
        results = await search_agent.search(query)
        results = results[:max_results]
        
        progress.update(task, description="Formatting results...")
    
    if not results:
        console.print(f"[yellow]No files found matching '{query}'[/yellow]")
        return
    
    # Display results based on format
    if output_format == "json":
        import json
        console.print(json.dumps(results, indent=2))
    elif output_format == "simple":
        for result in results:
            console.print(f"{result['file_path']}")
    else:
        _display_search_table(results, query)


def _display_search_table(results, query):
    """Display search results in a rich table."""
    table = Table(title=f"Search Results for '{query}'")
    table.add_column("File", style="cyan", no_wrap=True)
    table.add_column("Path", style="blue")
    table.add_column("Score", style="green", justify="center")
    table.add_column("Type", style="magenta", justify="center")
    table.add_column("Preview", style="white")
    
    for result in results:
        file_name = result.get("file_name", "")
        file_path = result.get("file_path", "")
        score = f"{result.get('similarity_score', 0):.3f}"
        search_type = result.get("search_type", "")
        preview = result.get("content_snippet", "")[:50] + "..." if result.get("content_snippet") else ""
        
        # Truncate long paths
        display_path = file_path
        if len(display_path) > 60:
            display_path = "..." + display_path[-57:]
        
        table.add_row(file_name, display_path, score, search_type, preview)
    
    console.print(table)


@app.command()
def index(
    path: Optional[str] = typer.Argument(None, help="Directory to index (optional for full reindex)"),
    full: bool = typer.Option(False, "--full", "-f", help="Perform full reindex"),
    incremental: bool = typer.Option(False, "--incremental", "-i", help="Perform incremental index")
):
    """Index files for searching."""
    asyncio.run(_index_async(path, full, incremental))


async def _index_async(path: Optional[str], full: bool, incremental: bool):
    """Async indexing implementation."""
    config = FinderConfig()
    config.ensure_directories()
    
    indexer = DocumentIndexer(config)
    indexer.load_or_create_index()
    
    indexing_agent = SimpleIndexingAgent(config, indexer)
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        
        if full:
            task = progress.add_task("Performing full reindex...", total=None)
            stats = await indexing_agent.full_reindex()
        elif incremental:
            task = progress.add_task("Performing incremental index...", total=None)
            stats = await indexing_agent.incremental_index()
        elif path:
            path_obj = Path(path)
            if not path_obj.exists():
                console.print(f"[red]Path does not exist: {path}[/red]")
                return
            
            task = progress.add_task(f"Indexing {path}...", total=None)
            stats = await indexer.index_directory(path_obj)
        else:
            console.print("[yellow]Please specify --full, --incremental, or provide a path to index.[/yellow]")
            return
    
    # Display results
    panel_content = f"""
[green]✓[/green] Files processed: {stats['processed']}
[green]✓[/green] Files indexed: {stats['indexed']}
[red]✗[/red] Errors: {stats['errors']}
"""
    
    console.print(Panel(panel_content, title="Indexing Complete", border_style="green"))


@app.command()
def stats():
    """Show indexing statistics."""
    config = FinderConfig()
    
    try:
        indexer = DocumentIndexer(config)
        indexer.load_or_create_index()
        
        stats = indexer.get_stats()
        
        table = Table(title="Enhanced Finder Statistics")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        
        table.add_row("Total Documents", str(stats['total_documents']))
        table.add_row("Total Chunks", str(stats['total_chunks']))
        table.add_row("Vector Count", str(stats['vector_count']))
        table.add_row("Index Size", f"{stats['index_size_mb']:.2f} MB")
        
        console.print(table)
        
        # Show configuration
        config_table = Table(title="Configuration")
        config_table.add_column("Setting", style="cyan")
        config_table.add_column("Value", style="blue")
        
        config_table.add_row("Supported Extensions", str(len(config.supported_extensions)))
        config_table.add_row("Max File Size", f"{config.max_file_size_mb} MB")
        config_table.add_row("Embedding Model", config.embedding_model)
        config_table.add_row("Max Search Results", str(config.max_search_results))
        
        console.print(config_table)
        
        # Show scan paths
        paths_table = Table(title="Scan Paths")
        paths_table.add_column("Path", style="blue")
        paths_table.add_column("Status", style="green")
        
        for scan_path in config.scan_paths:
            status = "✓ Exists" if scan_path.exists() else "✗ Missing"
            paths_table.add_row(str(scan_path), status)
        
        console.print(paths_table)
        
    except Exception as e:
        console.print(f"[red]Error getting statistics: {e}[/red]")


@app.command()
def config_cmd(
    action: str = typer.Argument(..., help="Action: add, remove, list"),
    path: Optional[str] = typer.Argument(None, help="Path to add or remove")
):
    """Configure scan paths."""
    config = FinderConfig()
    
    if action == "list":
        table = Table(title="Configured Scan Paths")
        table.add_column("#", style="cyan")
        table.add_column("Path", style="blue")
        table.add_column("Status", style="green")
        
        for i, scan_path in enumerate(config.scan_paths, 1):
            status = "✓ Exists" if scan_path.exists() else "✗ Missing"
            table.add_row(str(i), str(scan_path), status)
        
        console.print(table)
    
    elif action == "add":
        if not path:
            console.print("[red]Path is required for add action[/red]")
            return
        
        path_obj = Path(path).expanduser().resolve()
        if not path_obj.exists():
            console.print(f"[red]Path does not exist: {path}[/red]")
            return
        
        if path_obj not in config.scan_paths:
            config.scan_paths.append(path_obj)
            console.print(f"[green]Added path: {path_obj}[/green]")
            
            if Confirm.ask("Index this path now?"):
                asyncio.run(_index_async(str(path_obj), False, False))
        else:
            console.print(f"[yellow]Path already configured: {path_obj}[/yellow]")
    
    elif action == "remove":
        if not path:
            console.print("[red]Path is required for remove action[/red]")
            return
        
        path_obj = Path(path).expanduser().resolve()
        if path_obj in config.scan_paths:
            config.scan_paths.remove(path_obj)
            console.print(f"[green]Removed path: {path_obj}[/green]")
        else:
            console.print(f"[yellow]Path not found in configuration: {path_obj}[/yellow]")
    
    else:
        console.print("[red]Invalid action. Use 'add', 'remove', or 'list'[/red]")


@app.command()
def show(file_path: str = typer.Argument(..., help="Path to file to display")):
    """Show content of a specific file."""
    config = FinderConfig()
    indexer = DocumentIndexer(config)
    
    path_obj = Path(file_path)
    if not path_obj.exists():
        console.print(f"[red]File does not exist: {file_path}[/red]")
        return
    
    file_data = indexer.processor_manager.process_file(path_obj)
    
    if file_data.get("error"):
        console.print(f"[red]Error reading file: {file_data['error']}[/red]")
        return
    
    content = file_data.get("content", "")
    
    # Create info panel
    info_content = f"""
[cyan]File:[/cyan] {path_obj.name}
[cyan]Path:[/cyan] {file_path}
[cyan]Size:[/cyan] {file_data.get('file_size', 0)} bytes
[cyan]Type:[/cyan] {path_obj.suffix}
"""
    
    console.print(Panel(info_content, title="File Information", border_style="blue"))
    
    # Display content
    if len(content) > 5000:
        if Confirm.ask(f"File is large ({len(content)} characters). Show full content?"):
            console.print(Panel(content, title="File Content", border_style="green"))
        else:
            truncated = content[:5000] + "\n\n... (truncated)"
            console.print(Panel(truncated, title="File Content (Truncated)", border_style="yellow"))
    else:
        console.print(Panel(content, title="File Content", border_style="green"))


@app.command()
def clear_index(
    confirm: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt")
):
    """Clear the entire index and metadata database."""
    config = FinderConfig()
    
    if not confirm:
        console.print("[yellow]This will delete all indexed data and cannot be undone.[/yellow]")
        if not Confirm.ask("Are you sure you want to clear the index?"):
            console.print("[blue]Operation cancelled.[/blue]")
            return
    
    try:
        # Remove vector store files
        if config.vector_store_path.exists():
            import shutil
            shutil.rmtree(config.vector_store_path)
            console.print(f"[green]✓[/green] Removed vector store: {config.vector_store_path}")
        
        # Remove metadata database
        if config.metadata_db_path.exists():
            config.metadata_db_path.unlink()
            console.print(f"[green]✓[/green] Removed metadata database: {config.metadata_db_path}")
        
        # Remove index directory if empty
        if config.index_path.exists() and not any(config.index_path.iterdir()):
            config.index_path.rmdir()
            console.print(f"[green]✓[/green] Removed empty index directory: {config.index_path}")
        
        console.print(Panel(
            "[green]Index cleared successfully![/green]\n\nRun 'better-finder index --full' to rebuild the index.",
            title="Clear Complete",
            border_style="green"
        ))
    
    except Exception as e:
        console.print(f"[red]Error clearing index: {e}[/red]")


@app.command()
def remove_file(
    file_path: str = typer.Argument(..., help="Path to file to remove from index"),
    confirm: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt")
):
    """Remove a specific file from the index."""
    config = FinderConfig()
    path_obj = Path(file_path).resolve()
    
    if not confirm:
        if not Confirm.ask(f"Remove '{path_obj}' from index?"):
            console.print("[blue]Operation cancelled.[/blue]")
            return
    
    try:
        indexer = DocumentIndexer(config)
        indexer.load_or_create_index()
        
        # Check if file is in index
        if not indexer.is_file_indexed(path_obj):
            console.print(f"[yellow]File not found in index: {path_obj}[/yellow]")
            return
        
        # Remove from index (this would need to be implemented in indexer)
        removed = indexer.remove_file_from_index(path_obj)
        
        if removed:
            console.print(f"[green]✓[/green] Removed file from index: {path_obj}")
        else:
            console.print(f"[yellow]File was not found in index: {path_obj}[/yellow]")
            
    except Exception as e:
        console.print(f"[red]Error removing file from index: {e}[/red]")


@app.command()
def server():
    """Start the MCP server."""
    from .mcp_server import EnhancedFinderMCPServer
    
    console.print("[green]Starting Enhanced Finder MCP Server...[/green]")
    console.print("[blue]Connect your MCP client to use the server.[/blue]")
    
    server = EnhancedFinderMCPServer()
    asyncio.run(server.run())


def main():
    """Main entry point."""
    app()


if __name__ == "__main__":
    main()
"""Configuration settings for the Enhanced Finder."""

from pathlib import Path
from typing import List, Set
from pydantic import BaseModel


class FinderConfig(BaseModel):
    """Configuration for the Enhanced Finder."""
    
    # Index settings
    index_path: Path = Path.home() / ".enhanced_finder" / "index"
    vector_store_path: Path = Path.home() / ".enhanced_finder" / "vectors"
    metadata_db_path: Path = Path.home() / ".enhanced_finder" / "metadata.db"
    
    # File types to index
    supported_extensions: Set[str] = {
        ".pdf", ".txt", ".md", ".doc", ".docx", 
        ".xlsx", ".xls", ".csv", ".json", ".xml",
        ".py", ".js", ".ts", ".html", ".css",
        ".yaml", ".yml", ".toml", ".ini"
    }
    
    # Directories to ignore
    ignored_directories: Set[str] = {
        ".git", ".svn", ".hg", "__pycache__", ".pytest_cache",
        "node_modules", ".venv", "venv", ".env",
        "Library/Caches", "Library/Logs", ".Trash",
        "System", "Applications", ".DS_Store"
    }
    
    # File size limits (in MB)
    max_file_size_mb: int = 100
    
    # Indexing settings
    chunk_size: int = 1000
    chunk_overlap: int = 200
    embedding_model: str = "all-MiniLM-L6-v2"
    
    # Search settings
    max_search_results: int = 20
    similarity_threshold: float = 0.7
    
    # Paths to scan
    scan_paths: List[Path] = [
        Path.home() / "Documents",
        Path.home() / "Desktop",
        Path.home() / "Downloads"
    ]
    
    def ensure_directories(self):
        """Ensure all required directories exist."""
        self.index_path.mkdir(parents=True, exist_ok=True)
        self.vector_store_path.mkdir(parents=True, exist_ok=True)
        self.metadata_db_path.parent.mkdir(parents=True, exist_ok=True)
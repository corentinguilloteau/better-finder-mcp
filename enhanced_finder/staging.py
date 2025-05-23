"""Staging system for better-finder similar to Git."""

import json
import fnmatch
from pathlib import Path
from typing import Set, List, Dict, Any
from datetime import datetime

from .config import FinderConfig


class StagingManager:
    """Manages staging of files and directories for indexing."""
    
    def __init__(self, config: FinderConfig, working_dir: Path = None):
        self.config = config
        self.working_dir = working_dir or Path.cwd()
        self.staging_file = self.config.index_path / "staging.json"
        self.staged_paths: Set[str] = set()
        self.load_staging()
    
    def load_staging(self):
        """Load staged paths from disk."""
        if self.staging_file.exists():
            try:
                with open(self.staging_file, 'r') as f:
                    data = json.load(f)
                    self.staged_paths = set(data.get('staged_paths', []))
            except (json.JSONDecodeError, KeyError):
                self.staged_paths = set()
        else:
            self.staged_paths = set()
    
    def save_staging(self):
        """Save staged paths to disk."""
        self.config.ensure_directories()
        data = {
            'staged_paths': list(self.staged_paths),
            'last_updated': datetime.now().isoformat()
        }
        with open(self.staging_file, 'w') as f:
            json.dump(data, f, indent=2)
    
    def load_betterfinderignore(self, directory: Path) -> Set[str]:
        """Load ignore patterns from .betterfinderignore file."""
        ignore_patterns = set()
        ignore_file = directory / ".betterfinderignore"
        
        if ignore_file.exists():
            try:
                with open(ignore_file, 'r') as f:
                    for line in f:
                        pattern = line.strip()
                        if pattern and not pattern.startswith('#'):
                            ignore_patterns.add(pattern)
            except Exception as e:
                print(f"Warning: Could not read .betterfinderignore: {e}")
        
        return ignore_patterns
    
    def should_ignore_path(self, file_path: Path, ignore_patterns: Set[str] = None) -> bool:
        """Check if a path should be ignored based on various rules (excluding extension check)."""
        # Check ignored directories from config
        path_parts = file_path.parts
        for part in path_parts:
            if part in self.config.ignored_directories:
                return True
        
        # Check .betterfinderignore patterns
        if ignore_patterns:
            try:
                relative_path = str(file_path.relative_to(self.working_dir))
                for pattern in ignore_patterns:
                    if fnmatch.fnmatch(relative_path, pattern) or fnmatch.fnmatch(file_path.name, pattern):
                        return True
            except ValueError:
                # Path is not relative to working directory, check filename patterns only
                for pattern in ignore_patterns:
                    if fnmatch.fnmatch(file_path.name, pattern):
                        return True
        
        return False
    
    def is_supported_extension(self, file_path: Path) -> bool:
        """Check if file has a supported extension."""
        return file_path.suffix.lower() in self.config.supported_extensions
    
    def add_path(self, path: str) -> Dict[str, Any]:
        """Add a path or pattern to staging."""
        target_path = Path(path).resolve()
        
        if not target_path.exists():
            return {"error": f"Path does not exist: {path}"}
        
        # Load ignore patterns from current directory
        ignore_patterns = self.load_betterfinderignore(self.working_dir)
        
        added_files = []
        ignored_files = []
        unsupported_files = []
        
        if target_path.is_file():
            if not self.is_supported_extension(target_path):
                unsupported_files.append(str(target_path))
            elif self.should_ignore_path(target_path, ignore_patterns):
                ignored_files.append(str(target_path))
            else:
                self.staged_paths.add(str(target_path))
                added_files.append(str(target_path))
        
        elif target_path.is_dir():
            # Add all files in directory recursively
            for file_path in target_path.rglob("*"):
                if file_path.is_file():
                    if not self.is_supported_extension(file_path):
                        unsupported_files.append(str(file_path))
                    elif self.should_ignore_path(file_path, ignore_patterns):
                        ignored_files.append(str(file_path))
                    else:
                        self.staged_paths.add(str(file_path))
                        added_files.append(str(file_path))
        
        self.save_staging()
        
        return {
            "added_files": added_files,
            "ignored_files": ignored_files,
            "unsupported_files": unsupported_files,
            "total_added": len(added_files),
            "total_ignored": len(ignored_files),
            "total_unsupported": len(unsupported_files)
        }
    
    def remove_path(self, path: str) -> Dict[str, Any]:
        """Remove a path from staging."""
        target_path = Path(path).resolve()
        removed_files = []
        
        if target_path.is_file():
            path_str = str(target_path)
            if path_str in self.staged_paths:
                self.staged_paths.remove(path_str)
                removed_files.append(path_str)
        
        elif target_path.is_dir():
            # Remove all files in directory
            to_remove = []
            for staged_path in self.staged_paths:
                if Path(staged_path).is_relative_to(target_path):
                    to_remove.append(staged_path)
            
            for path_str in to_remove:
                self.staged_paths.remove(path_str)
                removed_files.append(path_str)
        
        else:
            # Try exact match removal
            if path in self.staged_paths:
                self.staged_paths.remove(path)
                removed_files.append(path)
        
        self.save_staging()
        
        return {
            "removed_files": removed_files,
            "total_removed": len(removed_files)
        }
    
    def get_status(self) -> Dict[str, Any]:
        """Get current staging status."""
        # Check which staged files still exist
        existing_files = []
        missing_files = []
        
        for path_str in self.staged_paths:
            path = Path(path_str)
            if path.exists():
                existing_files.append(path_str)
            else:
                missing_files.append(path_str)
        
        # Remove missing files from staging
        for path_str in missing_files:
            self.staged_paths.discard(path_str)
        
        if missing_files:
            self.save_staging()
        
        # Group by file type
        file_types = {}
        for path_str in existing_files:
            path = Path(path_str)
            ext = path.suffix.lower()
            if ext not in file_types:
                file_types[ext] = []
            file_types[ext].append(path_str)
        
        return {
            "staged_files": existing_files,
            "missing_files": missing_files,
            "total_staged": len(existing_files),
            "file_types": file_types,
            "staging_file": str(self.staging_file)
        }
    
    def get_staged_files(self) -> List[Path]:
        """Get list of staged file paths that exist."""
        existing_files = []
        for path_str in self.staged_paths:
            path = Path(path_str)
            if path.exists():
                existing_files.append(path)
        return existing_files
    
    def clear_staging(self):
        """Clear all staged files."""
        self.staged_paths.clear()
        self.save_staging()
    
    def is_staged(self, file_path: Path) -> bool:
        """Check if a file is currently staged."""
        return str(file_path.resolve()) in self.staged_paths
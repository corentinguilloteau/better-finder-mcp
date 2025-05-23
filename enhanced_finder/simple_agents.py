"""Simplified agent implementation without complex LangGraph dependencies."""

import asyncio
from typing import List, Dict, Any, Optional
from pathlib import Path

from .indexer import DocumentIndexer
from .config import FinderConfig


class SimpleSearchAgent:
    """Simplified search agent for intelligent file operations."""
    
    def __init__(self, config: FinderConfig, indexer: DocumentIndexer):
        self.config = config
        self.indexer = indexer
    
    def _refine_query(self, query: str) -> str:
        """Refine the search query."""
        refined = query.strip().lower()
        
        # Add common synonyms and expansions
        expansions = {
            "doc": "document",
            "pic": "picture image photo",
            "vid": "video",
            "txt": "text",
            "pdf": "document",
            "excel": "spreadsheet xlsx csv",
            "presentation": "powerpoint ppt pptx slides"
        }
        
        for abbrev, expansion in expansions.items():
            if abbrev in refined:
                refined = refined.replace(abbrev, f"{abbrev} {expansion}")
        
        return refined
    
    def _filename_search(self, pattern: str, max_results: int = 20) -> List[Dict[str, Any]]:
        """Search files by filename pattern."""
        results = []
        pattern_lower = pattern.lower()
        
        for scan_path in self.config.scan_paths:
            if not scan_path.exists():
                continue
                
            for file_path in scan_path.rglob("*"):
                if file_path.is_file() and pattern_lower in file_path.name.lower():
                    results.append({
                        "file_path": str(file_path),
                        "file_name": file_path.name,
                        "similarity_score": 1.0,
                        "search_type": "filename",
                        "metadata": {"file_size": file_path.stat().st_size}
                    })
                    
                    if len(results) >= max_results:
                        break
        
        return results
    
    def _determine_search_strategy(self, query: str) -> str:
        """Determine the best search strategy for the query."""
        query_lower = query.lower()
        
        # Check for file extensions
        if any(ext in query_lower for ext in [".pdf", ".xlsx", ".doc", ".txt"]):
            return "filename"
        
        # Check for single word without spaces (likely filename)
        if len(query.split()) == 1 and not any(c.isspace() for c in query):
            return "both"  # Try both strategies
        
        return "semantic"
    
    async def search(self, query: str, filters: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """Execute the search workflow."""
        results = []
        strategy = self._determine_search_strategy(query)
        
        # Semantic search
        if strategy in ["semantic", "both"]:
            refined_query = self._refine_query(query)
            semantic_results = await self.indexer.search(refined_query, self.config.max_search_results)
            
            for result in semantic_results:
                result["search_type"] = "semantic"
            
            results.extend(semantic_results)
        
        # Filename search
        if strategy in ["filename", "both"]:
            filename_results = self._filename_search(query, 10)
            results.extend(filename_results)
        
        # Deduplicate results
        seen_paths = set()
        unique_results = []
        
        for result in results:
            path = result.get("file_path", "")
            if path not in seen_paths:
                seen_paths.add(path)
                unique_results.append(result)
        
        # Sort by similarity score and search type priority
        def sort_key(result):
            score = result.get("similarity_score", 0)
            search_type = result.get("search_type", "")
            
            # Boost filename matches
            if search_type == "filename":
                score += 0.2
            
            return score
        
        unique_results.sort(key=sort_key, reverse=True)
        
        # Limit results
        return unique_results[:self.config.max_search_results]


class SimpleIndexingAgent:
    """Simplified agent for managing file indexing operations."""
    
    def __init__(self, config: FinderConfig, indexer: DocumentIndexer):
        self.config = config
        self.indexer = indexer
    
    async def full_reindex(self) -> Dict[str, Any]:
        """Perform a full reindex of all configured paths."""
        print("Starting full reindex...")
        
        total_stats = {"processed": 0, "indexed": 0, "errors": 0}
        
        for scan_path in self.config.scan_paths:
            if scan_path.exists():
                print(f"Indexing {scan_path}...")
                stats = await self.indexer.index_directory(scan_path)
                
                total_stats["processed"] += stats["processed"]
                total_stats["indexed"] += stats["indexed"]
                total_stats["errors"] += stats["errors"]
                
                print(f"Completed {scan_path}: {stats}")
        
        print("Full reindex completed!")
        return total_stats
    
    async def incremental_index(self) -> Dict[str, Any]:
        """Perform incremental indexing of new/modified files."""
        print("Starting incremental indexing...")
        
        total_stats = {"processed": 0, "indexed": 0, "errors": 0}
        
        for scan_path in self.config.scan_paths:
            if scan_path.exists():
                for file_path in scan_path.rglob("*"):
                    if file_path.is_file() and not self.indexer.is_file_indexed(file_path):
                        total_stats["processed"] += 1
                        try:
                            if await self.indexer.index_file(file_path):
                                total_stats["indexed"] += 1
                        except Exception as e:
                            total_stats["errors"] += 1
                            print(f"Error indexing {file_path}: {e}")
        
        return total_stats
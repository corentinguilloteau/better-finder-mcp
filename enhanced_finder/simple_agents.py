"""Simplified agent implementation without complex LangGraph dependencies."""

import asyncio
import re
from typing import List, Dict, Any, Optional
from pathlib import Path
from difflib import SequenceMatcher

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
    
    def _fuzzy_score(self, text1: str, text2: str) -> float:
        """Calculate fuzzy similarity score between two strings."""
        return SequenceMatcher(None, text1.lower(), text2.lower()).ratio()
    
    def _keyword_match_score(self, query: str, content: str) -> float:
        """Calculate keyword matching score."""
        query_words = set(re.findall(r'\w+', query.lower()))
        content_words = set(re.findall(r'\w+', content.lower()))
        
        if not query_words:
            return 0.0
        
        matches = len(query_words.intersection(content_words))
        return matches / len(query_words)
    
    def _filename_search(self, pattern: str, max_results: int = 20) -> List[Dict[str, Any]]:
        """Search files by filename pattern with fuzzy matching."""
        results = []
        pattern_lower = pattern.lower()
        
        for scan_path in self.config.scan_paths:
            if not scan_path.exists():
                continue
                
            for file_path in scan_path.rglob("*"):
                if not file_path.is_file():
                    continue
                
                filename_lower = file_path.name.lower()
                
                # Exact substring match
                if pattern_lower in filename_lower:
                    score = 1.0
                else:
                    # Fuzzy match
                    score = self._fuzzy_score(pattern_lower, filename_lower)
                    if score < 0.6:  # Skip low similarity matches
                        continue
                
                # Keyword match in filename
                keyword_score = self._keyword_match_score(pattern, file_path.name)
                final_score = max(score, keyword_score)
                
                if final_score >= 0.6:
                    results.append({
                        "file_path": str(file_path),
                        "file_name": file_path.name,
                        "similarity_score": final_score,
                        "search_type": "filename",
                        "metadata": {"file_size": file_path.stat().st_size}
                    })
                    
                    if len(results) >= max_results:
                        break
        
        return sorted(results, key=lambda x: x["similarity_score"], reverse=True)
    
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
    
    def _hybrid_score_combine(self, semantic_score: float, keyword_score: float, filename_score: float = 0.0) -> float:
        """Combine different search scores using weighted average."""
        # Weights for different search types
        semantic_weight = 0.5
        keyword_weight = 0.3  
        filename_weight = 0.2
        
        return (semantic_score * semantic_weight + 
                keyword_score * keyword_weight + 
                filename_score * filename_weight)
    
    async def search(self, query: str, filters: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """Execute hybrid search workflow combining semantic, keyword, and filename matching."""
        all_results = {}  # Use dict to track best score per file
        strategy = self._determine_search_strategy(query)
        
        # Semantic search
        if strategy in ["semantic", "both"]:
            refined_query = self._refine_query(query)
            semantic_results = await self.indexer.search(refined_query, self.config.max_search_results * 2)
            
            for result in semantic_results:
                path = result.get("file_path", "")
                semantic_score = result.get("similarity_score", 0)
                
                # Add keyword matching score for semantic results
                content = result.get("content_snippet", "")
                keyword_score = self._keyword_match_score(query, content)
                
                # Combine scores
                hybrid_score = self._hybrid_score_combine(semantic_score, keyword_score)
                
                if path not in all_results or all_results[path]["similarity_score"] < hybrid_score:
                    result["similarity_score"] = hybrid_score
                    result["search_type"] = "hybrid_semantic"
                    all_results[path] = result
        
        # Filename search with fuzzy matching
        if strategy in ["filename", "both"]:
            filename_results = self._filename_search(query, 15)
            
            for result in filename_results:
                path = result.get("file_path", "")
                filename_score = result.get("similarity_score", 0)
                
                if path in all_results:
                    # Boost existing result with filename match
                    existing = all_results[path]
                    existing_score = existing.get("similarity_score", 0)
                    boosted_score = max(existing_score + 0.2, filename_score)
                    existing["similarity_score"] = boosted_score
                    existing["search_type"] = "hybrid_combined"
                else:
                    # New filename-only result
                    result["search_type"] = "filename_fuzzy"
                    all_results[path] = result
        
        # Convert to list and sort by score
        final_results = list(all_results.values())
        final_results.sort(key=lambda x: x.get("similarity_score", 0), reverse=True)
        
        # Apply similarity threshold and limit results
        filtered_results = [
            r for r in final_results 
            if r.get("similarity_score", 0) >= 0.3  # Lower threshold for better recall
        ]
        
        return filtered_results[:self.config.max_search_results]


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
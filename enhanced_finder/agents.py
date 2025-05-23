"""Agent orchestration using LangGraph for intelligent file operations."""

import asyncio
from typing import List, Dict, Any, Optional
from pathlib import Path

from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain.tools import BaseTool
from langchain_core.pydantic_v1 import BaseModel, Field
from langchain_core.tools import ToolException

from .indexer import DocumentIndexer
from .config import FinderConfig


class SearchState(BaseModel):
    """State for the search agent."""
    query: str
    results: List[Dict[str, Any]] = Field(default_factory=list)
    refined_query: Optional[str] = None
    search_type: str = "semantic"  # semantic, filename, content
    filters: Dict[str, Any] = Field(default_factory=dict)
    step_count: int = 0
    max_steps: int = 5


class FileSearchTool(BaseTool):
    """Tool for semantic file search."""
    
    name = "file_search"
    description = "Search for files using semantic similarity"
    
    def __init__(self, indexer: DocumentIndexer):
        super().__init__()
        self.indexer = indexer
    
    def _run(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """Run semantic search."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self.indexer.search(query, max_results))
        finally:
            loop.close()
    
    async def _arun(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """Run semantic search asynchronously."""
        return await self.indexer.search(query, max_results)


class FilenameSearchTool(BaseTool):
    """Tool for filename-based search."""
    
    name = "filename_search"
    description = "Search for files by filename patterns"
    
    def __init__(self, config: FinderConfig):
        super().__init__()
        self.config = config
    
    def _run(self, pattern: str, max_results: int = 20) -> List[Dict[str, Any]]:
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
    
    async def _arun(self, pattern: str, max_results: int = 20) -> List[Dict[str, Any]]:
        """Search files by filename pattern asynchronously."""
        return self._run(pattern, max_results)


class QueryRefinementTool(BaseTool):
    """Tool for refining search queries."""
    
    name = "refine_query"
    description = "Refine and expand search queries for better results"
    
    def _run(self, query: str, search_context: str = "") -> str:
        """Refine the search query."""
        # Simple query refinement logic
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
    
    async def _arun(self, query: str, search_context: str = "") -> str:
        """Refine the search query asynchronously."""
        return self._run(query, search_context)


class SearchAgent:
    """Intelligent search agent using LangGraph."""
    
    def __init__(self, config: FinderConfig, indexer: DocumentIndexer):
        self.config = config
        self.indexer = indexer
        
        # Initialize tools
        self.tools = [
            FileSearchTool(indexer),
            FilenameSearchTool(config),
            QueryRefinementTool()
        ]
        
        self.tool_node = ToolNode(self.tools)
        
        # Build the graph
        self.graph = self._build_graph()
    
    def _build_graph(self) -> StateGraph:
        """Build the LangGraph workflow."""
        workflow = StateGraph(SearchState)
        
        # Add nodes
        workflow.add_node("analyze_query", self._analyze_query)
        workflow.add_node("semantic_search", self._semantic_search)
        workflow.add_node("filename_search", self._filename_search)
        workflow.add_node("refine_results", self._refine_results)
        workflow.add_node("combine_results", self._combine_results)
        
        # Add edges
        workflow.set_entry_point("analyze_query")
        
        workflow.add_conditional_edges(
            "analyze_query",
            self._should_use_semantic_search,
            {
                "semantic": "semantic_search",
                "filename": "filename_search",
                "both": "semantic_search"
            }
        )
        
        workflow.add_edge("semantic_search", "filename_search")
        workflow.add_edge("filename_search", "combine_results")
        workflow.add_edge("combine_results", "refine_results")
        workflow.add_edge("refine_results", END)
        
        return workflow.compile()
    
    def _analyze_query(self, state: SearchState) -> SearchState:
        """Analyze the search query to determine strategy."""
        query = state.query.lower()
        
        # Determine search type based on query characteristics
        if any(ext in query for ext in [".pdf", ".xlsx", ".doc", ".txt"]):
            state.search_type = "filename"
        elif len(query.split()) == 1 and not any(c.isspace() for c in query):
            state.search_type = "filename"
        else:
            state.search_type = "semantic"
        
        state.step_count += 1
        return state
    
    def _should_use_semantic_search(self, state: SearchState) -> str:
        """Decide whether to use semantic search."""
        if state.search_type == "filename":
            return "filename"
        elif state.search_type == "semantic":
            return "semantic"
        else:
            return "both"
    
    async def _semantic_search(self, state: SearchState) -> SearchState:
        """Perform semantic search."""
        try:
            # Refine query if needed
            if not state.refined_query:
                refine_tool = next(t for t in self.tools if t.name == "refine_query")
                state.refined_query = await refine_tool._arun(state.query)
            
            # Perform semantic search
            search_tool = next(t for t in self.tools if t.name == "file_search")
            semantic_results = await search_tool._arun(
                state.refined_query or state.query,
                max_results=15
            )
            
            # Mark results as semantic
            for result in semantic_results:
                result["search_type"] = "semantic"
            
            state.results.extend(semantic_results)
            
        except Exception as e:
            print(f"Error in semantic search: {e}")
        
        state.step_count += 1
        return state
    
    async def _filename_search(self, state: SearchState) -> SearchState:
        """Perform filename-based search."""
        try:
            filename_tool = next(t for t in self.tools if t.name == "filename_search")
            filename_results = await filename_tool._arun(
                pattern=state.query,
                max_results=10
            )
            state.results.extend(filename_results)
            
        except Exception as e:
            print(f"Error in filename search: {e}")
        
        state.step_count += 1
        return state
    
    async def _combine_results(self, state: SearchState) -> SearchState:
        """Combine and deduplicate results."""
        # Remove duplicates based on file path
        seen_paths = set()
        unique_results = []
        
        for result in state.results:
            path = result.get("file_path", "")
            if path not in seen_paths:
                seen_paths.add(path)
                unique_results.append(result)
        
        state.results = unique_results
        state.step_count += 1
        return state
    
    async def _refine_results(self, state: SearchState) -> SearchState:
        """Refine and rank final results."""
        # Sort by similarity score and search type priority
        def sort_key(result):
            score = result.get("similarity_score", 0)
            search_type = result.get("search_type", "")
            
            # Boost filename matches
            if search_type == "filename":
                score += 0.2
            
            return score
        
        state.results.sort(key=sort_key, reverse=True)
        
        # Limit results
        state.results = state.results[:self.config.max_search_results]
        
        state.step_count += 1
        return state
    
    async def search(self, query: str, filters: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """Execute the search workflow."""
        initial_state = SearchState(
            query=query,
            filters=filters or {}
        )
        
        final_state = await self.graph.ainvoke(initial_state)
        return final_state.results


class IndexingAgent:
    """Agent for managing file indexing operations."""
    
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
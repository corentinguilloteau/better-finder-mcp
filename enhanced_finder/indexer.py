"""File indexing and vector storage functionality."""

import os
import json
import sqlite3
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
from langchain.text_splitter import RecursiveCharacterTextSplitter

from .config import FinderConfig
from .file_processors import FileProcessorManager


class DocumentIndexer:
    """Handles document indexing and vector storage."""
    
    def __init__(self, config: FinderConfig):
        self.config = config
        self.config.ensure_directories()
        
        self.processor_manager = FileProcessorManager()
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=config.chunk_size,
            chunk_overlap=config.chunk_overlap
        )
        
        # Initialize embedding model
        self.embedding_model = SentenceTransformer(config.embedding_model)
        self.embedding_dim = self.embedding_model.get_sentence_embedding_dimension()
        
        # Initialize FAISS index
        self.index = None
        self.document_metadata = []
        
        # Initialize SQLite database for metadata
        self.init_metadata_db()
        
    def init_metadata_db(self):
        """Initialize SQLite database for storing file metadata."""
        self.conn = sqlite3.connect(str(self.config.metadata_db_path))
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT UNIQUE,
                file_name TEXT,
                file_size INTEGER,
                modified_time REAL,
                content_hash TEXT,
                chunk_count INTEGER,
                indexed_time REAL,
                metadata TEXT
            )
        """)
        
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER,
                chunk_index INTEGER,
                content TEXT,
                embedding_index INTEGER,
                FOREIGN KEY (document_id) REFERENCES documents (id)
            )
        """)
        self.conn.commit()
    
    def load_or_create_index(self):
        """Load existing FAISS index or create a new one."""
        index_file = self.config.vector_store_path / "faiss.index"
        
        if index_file.exists():
            try:
                self.index = faiss.read_index(str(index_file))
                # Load document metadata
                metadata_file = self.config.vector_store_path / "metadata.json"
                if metadata_file.exists():
                    with open(metadata_file, 'r') as f:
                        self.document_metadata = json.load(f)
                print(f"Loaded existing index with {self.index.ntotal} vectors")
            except Exception as e:
                print(f"Error loading index: {e}. Creating new index.")
                self.index = faiss.IndexFlatIP(self.embedding_dim)
                self.document_metadata = []
        else:
            self.index = faiss.IndexFlatIP(self.embedding_dim)
            self.document_metadata = []
    
    def save_index(self):
        """Save FAISS index and metadata to disk."""
        index_file = self.config.vector_store_path / "faiss.index"
        metadata_file = self.config.vector_store_path / "metadata.json"
        
        faiss.write_index(self.index, str(index_file))
        with open(metadata_file, 'w') as f:
            json.dump(self.document_metadata, f)
    
    def should_index_file(self, file_path: Path) -> bool:
        """Check if a file should be indexed."""
        # Check file extension
        if file_path.suffix.lower() not in self.config.supported_extensions:
            return False
        
        # Check file size
        try:
            size_mb = file_path.stat().st_size / (1024 * 1024)
            if size_mb > self.config.max_file_size_mb:
                return False
        except OSError:
            return False
        
        # Check if file is in ignored directory
        for parent in file_path.parents:
            if parent.name in self.config.ignored_directories:
                return False
        
        return True
    
    def is_file_indexed(self, file_path: Path) -> bool:
        """Check if file is already indexed and up to date."""
        cursor = self.conn.execute(
            "SELECT modified_time FROM documents WHERE file_path = ?",
            (str(file_path),)
        )
        result = cursor.fetchone()
        
        if result:
            indexed_mtime = result[0]
            current_mtime = file_path.stat().st_mtime
            return abs(current_mtime - indexed_mtime) < 1.0  # 1 second tolerance
        
        return False
    
    async def index_file(self, file_path: Path) -> bool:
        """Index a single file."""
        try:
            if not self.should_index_file(file_path) or self.is_file_indexed(file_path):
                return False
            
            # Process file content
            file_data = self.processor_manager.process_file(file_path)
            
            if not file_data.get("content") or file_data.get("error"):
                return False
            
            # Split content into chunks
            chunks = self.text_splitter.split_text(file_data["content"])
            
            if not chunks:
                return False
            
            # Generate embeddings
            embeddings = self.embedding_model.encode(chunks)
            embeddings = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)  # Normalize
            
            # Add to FAISS index
            start_idx = self.index.ntotal
            self.index.add(embeddings.astype(np.float32))
            
            # Store in database
            cursor = self.conn.execute("""
                INSERT OR REPLACE INTO documents 
                (file_path, file_name, file_size, modified_time, content_hash, chunk_count, indexed_time, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                str(file_path),
                file_path.name,
                file_data.get("file_size", 0),
                file_data.get("modified_time", 0),
                str(hash(file_data["content"])),
                len(chunks),
                datetime.now().timestamp(),
                json.dumps(file_data)
            ))
            
            document_id = cursor.lastrowid
            
            # Store chunks
            for i, chunk in enumerate(chunks):
                self.conn.execute("""
                    INSERT INTO chunks (document_id, chunk_index, content, embedding_index)
                    VALUES (?, ?, ?, ?)
                """, (document_id, i, chunk, start_idx + i))
            
            self.conn.commit()
            
            print(f"Indexed: {file_path} ({len(chunks)} chunks)")
            return True
            
        except Exception as e:
            print(f"Error indexing {file_path}: {e}")
            return False
    
    async def index_directory(self, directory: Path) -> Dict[str, int]:
        """Index all files in a directory recursively."""
        stats = {"processed": 0, "indexed": 0, "errors": 0}
        
        for file_path in directory.rglob("*"):
            if file_path.is_file():
                stats["processed"] += 1
                
                try:
                    if await self.index_file(file_path):
                        stats["indexed"] += 1
                except Exception as e:
                    stats["errors"] += 1
                    print(f"Error processing {file_path}: {e}")
                
                # Save index periodically
                if stats["indexed"] % 100 == 0:
                    self.save_index()
        
        self.save_index()
        return stats
    
    async def search(self, query: str, k: int = None) -> List[Dict[str, Any]]:
        """Search for documents similar to the query."""
        if k is None:
            k = self.config.max_search_results
        
        if self.index is None or self.index.ntotal == 0:
            return []
        
        # Generate query embedding
        query_embedding = self.embedding_model.encode([query])
        query_embedding = query_embedding / np.linalg.norm(query_embedding, axis=1, keepdims=True)
        
        # Search FAISS index
        scores, indices = self.index.search(query_embedding.astype(np.float32), k)
        
        results = []
        seen_documents = set()
        
        for score, idx in zip(scores[0], indices[0]):
            if score < self.config.similarity_threshold:
                continue
            
            # Get chunk information
            cursor = self.conn.execute("""
                SELECT c.content, c.document_id, d.file_path, d.file_name, d.metadata
                FROM chunks c
                JOIN documents d ON c.document_id = d.id
                WHERE c.embedding_index = ?
            """, (int(idx),))
            
            result = cursor.fetchone()
            if result and result[1] not in seen_documents:
                content, doc_id, file_path, file_name, metadata = result
                
                try:
                    metadata_dict = json.loads(metadata) if metadata else {}
                except json.JSONDecodeError:
                    metadata_dict = {}
                
                results.append({
                    "file_path": file_path,
                    "file_name": file_name,
                    "content_snippet": content[:200] + "..." if len(content) > 200 else content,
                    "similarity_score": float(score),
                    "metadata": metadata_dict
                })
                
                seen_documents.add(doc_id)
        
        return results
    
    def remove_file_from_index(self, file_path: Path) -> bool:
        """Remove a specific file from the index."""
        file_path_str = str(file_path.resolve())
        
        # Check if file exists in database
        cursor = self.conn.execute("SELECT id FROM documents WHERE file_path = ?", (file_path_str,))
        result = cursor.fetchone()
        
        if not result:
            return False
        
        doc_id = result[0]
        
        # Get all embedding indices for this document's chunks
        cursor = self.conn.execute("SELECT embedding_index FROM chunks WHERE document_id = ?", (doc_id,))
        embedding_indices = [row[0] for row in cursor.fetchall()]
        
        # Remove chunks from database
        self.conn.execute("DELETE FROM chunks WHERE document_id = ?", (doc_id,))
        
        # Remove document from database
        self.conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        self.conn.commit()
        
        # Note: FAISS doesn't support efficient removal of individual vectors
        # For proper cleanup, we'd need to rebuild the index without removed vectors
        # For now, we'll just mark them as removed in metadata
        print(f"Removed file from database: {file_path_str}")
        print("Note: Vector index still contains old embeddings. Consider running full reindex for cleanup.")
        
        return True
    
    def get_stats(self) -> Dict[str, Any]:
        """Get indexing statistics."""
        cursor = self.conn.execute("SELECT COUNT(*) FROM documents")
        doc_count = cursor.fetchone()[0]
        
        cursor = self.conn.execute("SELECT COUNT(*) FROM chunks")
        chunk_count = cursor.fetchone()[0]
        
        return {
            "total_documents": doc_count,
            "total_chunks": chunk_count,
            "vector_count": self.index.ntotal if self.index else 0,
            "index_size_mb": (self.config.vector_store_path / "faiss.index").stat().st_size / (1024 * 1024) if (self.config.vector_store_path / "faiss.index").exists() else 0
        }
    
    def close(self):
        """Close database connection."""
        if hasattr(self, 'conn'):
            self.conn.close()
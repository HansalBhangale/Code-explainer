"""
Chunk Data Access Object
Handles persistence and querying of code chunks in Neo4j
"""
from typing import List, Optional, Dict, Any
from src.models.schemas import Chunk
from src.database.neo4j_client import db
import logging
import json

logger = logging.getLogger(__name__)


class ChunkDAO:
    """DAO for chunk operations in Neo4j"""
    
    @staticmethod
    def batch_create_chunks(chunks: List[Chunk], embeddings: Optional[List[List[float]]] = None):
        """
        Batch create chunks with optional embeddings
        
        Args:
            chunks: List of Chunk instances
            embeddings: Optional list of embedding vectors (same length as chunks)
        """
        if not chunks:
            return
        
        # Prepare chunk data
        chunk_data = []
        for i, chunk in enumerate(chunks):
            data = {
                "chunk_id": chunk.chunk_id,
                "snapshot_id": chunk.snapshot_id,
                "file_id": chunk.file_id,
                "symbol_id": chunk.symbol_id,
                "parent_chunk_id": chunk.parent_chunk_id,
                "chunk_type": chunk.chunk_type.value,
                "content": chunk.content,
                "language": chunk.language,
                "start_line": chunk.start_line,
                "end_line": chunk.end_line,
                "metadata": json.dumps(chunk.metadata)
            }
            
            # Add embedding if provided
            if embeddings and i < len(embeddings):
                data["embedding"] = embeddings[i]
            
            chunk_data.append(data)
        
        # Create chunks and relationships
        query = """
        UNWIND $chunks AS chunk_data
        
        // Create chunk node
        CREATE (chunk:Chunk {
            chunk_id: chunk_data.chunk_id,
            snapshot_id: chunk_data.snapshot_id,
            file_id: chunk_data.file_id,
            symbol_id: chunk_data.symbol_id,
            parent_chunk_id: chunk_data.parent_chunk_id,
            chunk_type: chunk_data.chunk_type,
            content: chunk_data.content,
            language: chunk_data.language,
            start_line: chunk_data.start_line,
            end_line: chunk_data.end_line,
            metadata: chunk_data.metadata
        })
        
        // Set embedding if provided
        FOREACH (ignoreMe IN CASE WHEN chunk_data.embedding IS NOT NULL THEN [1] ELSE [] END |
            SET chunk.embedding = chunk_data.embedding
        )
        
        // Link to symbol
        WITH chunk, chunk_data
        MATCH (s:Symbol {symbol_id: chunk_data.symbol_id})
        CREATE (s)-[:HAS_CHUNK]->(chunk)
        
        // Link to file
        WITH chunk, chunk_data
        MATCH (f:File {file_id: chunk_data.file_id})
        CREATE (f)-[:CONTAINS_CHUNK]->(chunk)
        
        RETURN count(chunk) as created_count
        """
        
        result = db.execute_write(query, {"chunks": chunk_data})
        logger.info(f"Batch created {len(chunks)} chunks")
    
    @staticmethod
    def link_parent_child_chunks(snapshot_id: str):
        """Create PARENT_OF relationships between parent and child chunks"""
        query = """
        MATCH (parent:Chunk {snapshot_id: $snapshot_id, chunk_type: 'parent'})
        MATCH (child:Chunk {snapshot_id: $snapshot_id, chunk_type: 'child'})
        WHERE child.parent_chunk_id = parent.chunk_id
        CREATE (parent)-[:PARENT_OF]->(child)
        RETURN count(*) as linked_count
        """
        
        result = db.execute_write(query, {"snapshot_id": snapshot_id})
        logger.info(f"Linked parent-child chunks for snapshot {snapshot_id}")
    
    @staticmethod
    def get_chunk(chunk_id: str) -> Optional[Dict[str, Any]]:
        """Get chunk by ID"""
        query = """
        MATCH (c:Chunk {chunk_id: $chunk_id})
        OPTIONAL MATCH (c)<-[:HAS_CHUNK]-(s:Symbol)
        OPTIONAL MATCH (c)<-[:CONTAINS_CHUNK]-(f:File)
        RETURN c, s, f
        """
        
        result = db.execute_query(query, {"chunk_id": chunk_id})
        if result:
            record = result[0]
            return {
                "chunk": dict(record["c"]),
                "symbol": dict(record["s"]) if record["s"] else None,
                "file": dict(record["f"]) if record["f"] else None
            }
        return None
    
    @staticmethod
    def get_parent_chunk(chunk_id: str) -> Optional[Dict[str, Any]]:
        """Get parent chunk for a child chunk"""
        query = """
        MATCH (child:Chunk {chunk_id: $chunk_id})
        MATCH (parent:Chunk {chunk_id: child.parent_chunk_id})
        RETURN parent
        """
        
        result = db.execute_query(query, {"chunk_id": chunk_id})
        if result:
            return dict(result[0]["parent"])
        return None
    
    @staticmethod
    def get_chunks_for_symbol(symbol_id: str) -> List[Dict[str, Any]]:
        """Get all chunks for a symbol"""
        query = """
        MATCH (s:Symbol {symbol_id: $symbol_id})-[:HAS_CHUNK]->(c:Chunk)
        RETURN c
        ORDER BY c.chunk_type DESC  // Parent first, then child
        """
        
        result = db.execute_query(query, {"symbol_id": symbol_id})
        return [dict(record["c"]) for record in result]
    
    @staticmethod
    def vector_search(
        query_embedding: List[float], 
        snapshot_id: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Vector similarity search using Neo4j vector index
        
        Args:
            query_embedding: Query embedding vector
            snapshot_id: Snapshot to search within
            limit: Maximum results to return
            
        Returns:
            List of chunks with similarity scores
        """
        query = """
        CALL db.index.vector.queryNodes('chunk_embeddings', $limit, $embedding)
        YIELD node, score
        WHERE node.snapshot_id = $snapshot_id
        MATCH (node)<-[:HAS_CHUNK]-(s:Symbol)
        MATCH (s)<-[:DEFINES_SYMBOL]-(f:File)
        RETURN 
            node.chunk_id as chunk_id,
            node.content as content,
            node.chunk_type as chunk_type,
            score,
            s.symbol_id as symbol_id,
            s.name as symbol_name,
            s.kind as symbol_kind,
            f.path as file_path
        ORDER BY score DESC
        """
        
        result = db.execute_query(query, {
            "embedding": query_embedding,
            "snapshot_id": snapshot_id,
            "limit": limit
        })
        
        return [dict(record) for record in result]
    
    @staticmethod
    def fulltext_search(
        query: str,
        snapshot_id: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Full-text search using Neo4j fulltext index
        
        Args:
            query: Search query
            snapshot_id: Snapshot to search within
            limit: Maximum results to return
            
        Returns:
            List of chunks with relevance scores
        """
        cypher = """
        CALL db.index.fulltext.queryNodes('chunk_search', $query)
        YIELD node, score
        WHERE node.snapshot_id = $snapshot_id
        MATCH (node)<-[:HAS_CHUNK]-(s:Symbol)
        MATCH (s)<-[:DEFINES_SYMBOL]-(f:File)
        RETURN 
            node.chunk_id as chunk_id,
            node.content as content,
            node.chunk_type as chunk_type,
            score,
            s.symbol_id as symbol_id,
            s.name as symbol_name,
            s.kind as symbol_kind,
            f.path as file_path
        ORDER BY score DESC
        LIMIT $limit
        """
        
        result = db.execute_query(cypher, {
            "query": query,
            "snapshot_id": snapshot_id,
            "limit": limit
        })
        
        return [dict(record) for record in result]

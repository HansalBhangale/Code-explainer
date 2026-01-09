"""
Hybrid Retrieval Service
Combines lexical, vector, and graph-based search for RAG
"""
from typing import List, Dict, Any, Optional
from src.database.chunk_dao import ChunkDAO
from src.services.embedder import GeminiEmbedder
from src.database.neo4j_client import db
import logging

logger = logging.getLogger(__name__)


class HybridRetriever:
    """
    Hybrid retrieval combining:
    1. Lexical search (fulltext)
    2. Vector search (semantic similarity)
    3. Graph expansion (call graph relationships)
    """
    
    def __init__(self):
        self.embedder = GeminiEmbedder()
        self.chunk_dao = ChunkDAO()
    
    def search(
        self,
        query: str,
        snapshot_id: str,
        top_k: int = 10,
        lexical_weight: float = 0.3,
        vector_weight: float = 0.5,
        graph_weight: float = 0.2,
        expand_graph: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Hybrid search combining multiple strategies
        
        Args:
            query: Search query
            snapshot_id: Snapshot to search within
            top_k: Number of results to return
            lexical_weight: Weight for lexical search (0-1)
            vector_weight: Weight for vector search (0-1)
            graph_weight: Weight for graph expansion (0-1)
            expand_graph: Whether to expand results via call graph
            
        Returns:
            List of ranked chunks with metadata
        """
        logger.info(f"Hybrid search: '{query}' in snapshot {snapshot_id}")
        
        # 1. Lexical search (fulltext)
        lexical_results = self._lexical_search(query, snapshot_id, top_k * 2)
        logger.info(f"Lexical search found {len(lexical_results)} results")
        
        # 2. Vector search (semantic)
        vector_results = self._vector_search(query, snapshot_id, top_k * 2)
        logger.info(f"Vector search found {len(vector_results)} results")
        
        # 3. Combine and re-rank
        combined = self._combine_results(
            lexical_results,
            vector_results,
            lexical_weight,
            vector_weight
        )
        
        # 4. Graph expansion (optional)
        if expand_graph and combined:
            expanded = self._expand_via_graph(combined, snapshot_id, graph_weight)
            combined = self._merge_expanded(combined, expanded, graph_weight)
        
        # 5. Return top-k
        ranked = sorted(combined, key=lambda x: x['final_score'], reverse=True)[:top_k]
        
        logger.info(f"Returning {len(ranked)} results")
        return ranked
    
    def _lexical_search(
        self,
        query: str,
        snapshot_id: str,
        limit: int
    ) -> List[Dict[str, Any]]:
        """Fulltext search"""
        try:
            results = self.chunk_dao.fulltext_search(query, snapshot_id, limit)
            return [
                {
                    'chunk_id': r['chunk_id'],
                    'content': r['content'],
                    'chunk_type': r['chunk_type'],
                    'symbol_id': r['symbol_id'],
                    'symbol_name': r['symbol_name'],
                    'symbol_kind': r['symbol_kind'],
                    'file_path': r['file_path'],
                    'lexical_score': r['score'],
                    'vector_score': 0.0
                }
                for r in results
            ]
        except Exception as e:
            logger.error(f"Lexical search failed: {e}")
            return []
    
    def _vector_search(
        self,
        query: str,
        snapshot_id: str,
        limit: int
    ) -> List[Dict[str, Any]]:
        """Semantic vector search"""
        try:
            # Generate query embedding
            query_embedding = self.embedder.generate_query_embedding(query)
            
            # Search
            results = self.chunk_dao.vector_search(query_embedding, snapshot_id, limit)
            return [
                {
                    'chunk_id': r['chunk_id'],
                    'content': r['content'],
                    'chunk_type': r['chunk_type'],
                    'symbol_id': r['symbol_id'],
                    'symbol_name': r['symbol_name'],
                    'symbol_kind': r['symbol_kind'],
                    'file_path': r['file_path'],
                    'lexical_score': 0.0,
                    'vector_score': r['score']
                }
                for r in results
            ]
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            return []
    
    def _combine_results(
        self,
        lexical: List[Dict],
        vector: List[Dict],
        lexical_weight: float,
        vector_weight: float
    ) -> List[Dict[str, Any]]:
        """Combine and normalize scores from both searches"""
        # Normalize scores to 0-1 range
        def normalize_scores(results, score_key):
            if not results:
                return results
            max_score = max(r[score_key] for r in results)
            if max_score > 0:
                for r in results:
                    r[score_key] = r[score_key] / max_score
            return results
        
        lexical = normalize_scores(lexical, 'lexical_score')
        vector = normalize_scores(vector, 'vector_score')
        
        # Merge by chunk_id
        merged = {}
        
        for result in lexical + vector:
            chunk_id = result['chunk_id']
            if chunk_id not in merged:
                merged[chunk_id] = result.copy()
            else:
                # Combine scores
                merged[chunk_id]['lexical_score'] = max(
                    merged[chunk_id]['lexical_score'],
                    result['lexical_score']
                )
                merged[chunk_id]['vector_score'] = max(
                    merged[chunk_id]['vector_score'],
                    result['vector_score']
                )
        
        # Calculate final score
        for chunk_id, result in merged.items():
            result['final_score'] = (
                lexical_weight * result['lexical_score'] +
                vector_weight * result['vector_score']
            )
        
        return list(merged.values())
    
    def _expand_via_graph(
        self,
        results: List[Dict],
        snapshot_id: str,
        weight: float
    ) -> List[Dict[str, Any]]:
        """Expand results by following call graph relationships"""
        if not results:
            return []
        
        # Get symbol IDs from top results
        symbol_ids = [r['symbol_id'] for r in results[:5]]  # Expand top 5
        
        expanded = []
        
        with db.session() as session:
            # Find related symbols via call graph
            result = session.run("""
                MATCH (s:Symbol)
                WHERE s.symbol_id IN $symbol_ids
                
                // Find callers and callees
                OPTIONAL MATCH (s)-[:CALLS]->(callee:Symbol)
                WHERE callee.snapshot_id = $snapshot_id
                OPTIONAL MATCH (caller:Symbol)-[:CALLS]->(s)
                WHERE caller.snapshot_id = $snapshot_id
                
                WITH s, collect(DISTINCT callee) + collect(DISTINCT caller) as related
                UNWIND related as rel
                WITH rel
                WHERE rel IS NOT NULL
                
                // Get chunks for related symbols
                MATCH (rel)-[:HAS_CHUNK]->(c:Chunk)
                MATCH (c)<-[:CONTAINS_CHUNK]-(f:File)
                
                RETURN DISTINCT
                    c.chunk_id as chunk_id,
                    c.content as content,
                    c.chunk_type as chunk_type,
                    rel.symbol_id as symbol_id,
                    rel.name as symbol_name,
                    rel.kind as symbol_kind,
                    f.path as file_path
                LIMIT 20
            """, symbol_ids=symbol_ids, snapshot_id=snapshot_id)
            
            for r in result:
                expanded.append({
                    'chunk_id': r['chunk_id'],
                    'content': r['content'],
                    'chunk_type': r['chunk_type'],
                    'symbol_id': r['symbol_id'],
                    'symbol_name': r['symbol_name'],
                    'symbol_kind': r['symbol_kind'],
                    'file_path': r['file_path'],
                    'lexical_score': 0.0,
                    'vector_score': 0.0,
                    'graph_score': weight
                })
        
        logger.info(f"Graph expansion found {len(expanded)} related chunks")
        return expanded
    
    def _merge_expanded(
        self,
        original: List[Dict],
        expanded: List[Dict],
        graph_weight: float
    ) -> List[Dict[str, Any]]:
        """Merge expanded results with original"""
        merged = {r['chunk_id']: r for r in original}
        
        for exp in expanded:
            chunk_id = exp['chunk_id']
            if chunk_id not in merged:
                exp['final_score'] = graph_weight * exp['graph_score']
                merged[chunk_id] = exp
        
        return list(merged.values())

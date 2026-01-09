"""
RAG API Routes
Endpoints for hybrid search and chunk retrieval
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from src.services.retriever import HybridRetriever
from src.services.code_explainer import CodeExplainer
from src.database.chunk_dao import ChunkDAO
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/rag", tags=["RAG"])


class SearchRequest(BaseModel):
    """Search request model"""
    query: str = Field(..., description="Search query")
    snapshot_id: str = Field(..., description="Snapshot ID to search within")
    top_k: int = Field(default=10, ge=1, le=50, description="Number of results")
    lexical_weight: float = Field(default=0.3, ge=0, le=1)
    vector_weight: float = Field(default=0.5, ge=0, le=1)
    graph_weight: float = Field(default=0.2, ge=0, le=1)
    expand_graph: bool = Field(default=True, description="Enable graph expansion")


class ExplainedSearchRequest(SearchRequest):
    """Search request with AI explanation"""
    explain: bool = Field(default=True, description="Generate AI explanations")
    explain_top_n: int = Field(default=3, ge=1, le=10, description="Number of results to explain")


class SearchResult(BaseModel):
    """Search result model"""
    chunk_id: str
    content: str
    chunk_type: str
    symbol_id: str
    symbol_name: str
    symbol_kind: str
    file_path: str
    final_score: float
    lexical_score: float
    vector_score: float


class ExplainedSearchResult(SearchResult):
    """Search result with AI explanation"""
    explanation: Optional[str] = Field(None, description="AI-generated code explanation")
    language: Optional[str] = Field(None, description="Programming language")


class SearchResponse(BaseModel):
    """Search response model"""
    query: str
    results: List[SearchResult]
    total_results: int


class ExplainedSearchResponse(BaseModel):
    """Search response with AI explanations"""
    query: str
    results: List[ExplainedSearchResult]
    total_results: int


class ChunkDetail(BaseModel):
    """Detailed chunk information"""
    chunk_id: str
    content: str
    chunk_type: str
    language: str
    start_line: int
    end_line: int
    symbol: Optional[Dict[str, Any]]
    file: Optional[Dict[str, Any]]
    parent_chunk: Optional[Dict[str, Any]]


@router.post("/search", response_model=SearchResponse)
async def hybrid_search(request: SearchRequest):
    """
    Hybrid search combining lexical, vector, and graph-based retrieval
    
    Args:
        request: Search request with query and parameters
        
    Returns:
        Ranked search results with metadata
    """
    try:
        retriever = HybridRetriever()
        
        results = retriever.search(
            query=request.query,
            snapshot_id=request.snapshot_id,
            top_k=request.top_k,
            lexical_weight=request.lexical_weight,
            vector_weight=request.vector_weight,
            graph_weight=request.graph_weight,
            expand_graph=request.expand_graph
        )
        
        return SearchResponse(
            query=request.query,
            results=[SearchResult(**r) for r in results],
            total_results=len(results)
        )
        
    except Exception as e:
        logger.error(f"Search failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@router.post("/search/explain", response_model=ExplainedSearchResponse)
async def hybrid_search_with_explanation(request: ExplainedSearchRequest):
    """
    Hybrid search with AI-generated code explanations
    
    Args:
        request: Search request with explanation parameters
        
    Returns:
        Ranked search results with AI explanations for top results
    """
    try:
        # Perform hybrid search
        retriever = HybridRetriever()
        
        results = retriever.search(
            query=request.query,
            snapshot_id=request.snapshot_id,
            top_k=request.top_k,
            lexical_weight=request.lexical_weight,
            vector_weight=request.vector_weight,
            graph_weight=request.graph_weight,
            expand_graph=request.expand_graph
        )
        
        # Generate explanations for top N results
        if request.explain and results:
            explainer = CodeExplainer()
            
            # Get chunk details for top results
            chunk_dao = ChunkDAO()
            explained_results = []
            
            for i, result in enumerate(results):
                # Add language field
                chunk_data = chunk_dao.get_chunk(result['chunk_id'])
                if chunk_data:
                    result['language'] = chunk_data['chunk'].get('language', 'python')
                else:
                    result['language'] = 'python'
                
                # Generate explanation for top N
                if i < request.explain_top_n:
                    try:
                        explanation = explainer.explain_with_query_context(
                            code=result['content'],
                            symbol_name=result['symbol_name'],
                            symbol_kind=result['symbol_kind'],
                            file_path=result['file_path'],
                            query=request.query,
                            language=result['language']
                        )
                        result['explanation'] = explanation
                    except Exception as e:
                        logger.error(f"Failed to explain chunk {result['chunk_id']}: {e}")
                        result['explanation'] = "Explanation unavailable"
                else:
                    result['explanation'] = None
                
                explained_results.append(result)
            
            return ExplainedSearchResponse(
                query=request.query,
                results=[ExplainedSearchResult(**r) for r in explained_results],
                total_results=len(explained_results)
            )
        else:
            # No explanations requested
            return ExplainedSearchResponse(
                query=request.query,
                results=[ExplainedSearchResult(**r, explanation=None, language='python') for r in results],
                total_results=len(results)
            )
        
    except Exception as e:
        logger.error(f"Explained search failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Explained search failed: {str(e)}")


@router.get("/chunks/{chunk_id}", response_model=ChunkDetail)
async def get_chunk(chunk_id: str):
    """
    Get detailed information about a specific chunk
    
    Args:
        chunk_id: Chunk ID
        
    Returns:
        Chunk details with symbol, file, and parent chunk info
    """
    try:
        chunk_dao = ChunkDAO()
        chunk_data = chunk_dao.get_chunk(chunk_id)
        
        if not chunk_data:
            raise HTTPException(status_code=404, detail="Chunk not found")
        
        chunk = chunk_data['chunk']
        
        # Get parent chunk if this is a child
        parent_chunk = None
        if chunk.get('chunk_type') == 'child' and chunk.get('parent_chunk_id'):
            parent_chunk = chunk_dao.get_parent_chunk(chunk_id)
        
        return ChunkDetail(
            chunk_id=chunk['chunk_id'],
            content=chunk['content'],
            chunk_type=chunk['chunk_type'],
            language=chunk['language'],
            start_line=chunk['start_line'],
            end_line=chunk['end_line'],
            symbol=chunk_data['symbol'],
            file=chunk_data['file'],
            parent_chunk=parent_chunk
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get chunk: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get chunk: {str(e)}")


@router.get("/chunks/symbol/{symbol_id}")
async def get_chunks_for_symbol(symbol_id: str):
    """
    Get all chunks for a specific symbol
    
    Args:
        symbol_id: Symbol ID
        
    Returns:
        List of chunks (parent and child)
    """
    try:
        chunk_dao = ChunkDAO()
        chunks = chunk_dao.get_chunks_for_symbol(symbol_id)
        
        return {
            "symbol_id": symbol_id,
            "chunks": chunks,
            "total": len(chunks)
        }
        
    except Exception as e:
        logger.error(f"Failed to get chunks for symbol: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get chunks: {str(e)}")

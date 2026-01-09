"""
Call Graph API Routes
Provides endpoints for querying function call relationships
"""
from fastapi import APIRouter, HTTPException, Query
from typing import List, Dict, Any
from src.database.call_graph_dao import CallGraphDAO
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/call-graph", tags=["call-graph"])


@router.get("/symbols/{symbol_id}/callers")
async def get_callers(symbol_id: str):
    """Get all symbols that call this symbol
    
    Args:
        symbol_id: Symbol ID to find callers for
        
    Returns:
        List of caller symbols with call information
    """
    try:
        callers = CallGraphDAO.get_callers(symbol_id)
        return {
            "symbol_id": symbol_id,
            "caller_count": len(callers),
            "callers": callers
        }
    except Exception as e:
        logger.error(f"Failed to get callers for {symbol_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/symbols/{symbol_id}/callees")
async def get_callees(symbol_id: str):
    """Get all symbols called by this symbol
    
    Args:
        symbol_id: Symbol ID to find callees for
        
    Returns:
        List of callee symbols with call information
    """
    try:
        callees = CallGraphDAO.get_callees(symbol_id)
        return {
            "symbol_id": symbol_id,
            "callee_count": len(callees),
            "callees": callees
        }
    except Exception as e:
        logger.error(f"Failed to get callees for {symbol_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/symbols/{symbol_id}/graph")
async def get_call_graph(
    symbol_id: str,
    depth: int = Query(default=2, ge=1, le=5, description="Graph traversal depth")
):
    """Get call graph centered on this symbol
    
    Args:
        symbol_id: Symbol ID to center graph on
        depth: How many levels deep to traverse (1-5)
        
    Returns:
        Call graph with nodes and edges
    """
    try:
        graph = CallGraphDAO.get_call_graph(symbol_id, depth)
        return {
            "symbol_id": symbol_id,
            "depth": depth,
            "node_count": len(graph["nodes"]),
            "edge_count": len(graph["edges"]),
            "graph": graph
        }
    except Exception as e:
        logger.error(f"Failed to get call graph for {symbol_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

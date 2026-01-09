"""
Type Information API Routes
Provides endpoints for querying type annotations
"""
from fastapi import APIRouter, HTTPException, Query
from typing import List, Dict, Any, Optional
from src.database.type_dao import TypeDAO
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/types", tags=["types"])


@router.get("/symbols/{symbol_id}/type")
async def get_symbol_type(symbol_id: str):
    """Get type annotation for a symbol
    
    Args:
        symbol_id: Symbol ID to get type for
        
    Returns:
        Type annotation information
    """
    try:
        type_info = TypeDAO.get_symbol_type(symbol_id)
        if not type_info:
            raise HTTPException(status_code=404, detail="No type annotation found for this symbol")
        
        return {
            "symbol_id": symbol_id,
            "type": type_info
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get type for {symbol_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/snapshots/{snapshot_id}/types/{type_name}")
async def find_symbols_by_type(snapshot_id: str, type_name: str):
    """Find all symbols with a specific type
    
    Args:
        snapshot_id: Snapshot ID to search in
        type_name: Type name to search for
        
    Returns:
        List of symbols with this type
    """
    try:
        symbols = TypeDAO.find_symbols_by_type(snapshot_id, type_name)
        return {
            "snapshot_id": snapshot_id,
            "type_name": type_name,
            "symbol_count": len(symbols),
            "symbols": symbols
        }
    except Exception as e:
        logger.error(f"Failed to find symbols by type {type_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/snapshots/{snapshot_id}/type-stats")
async def get_type_usage_stats(snapshot_id: str):
    """Get statistics on type usage in a snapshot
    
    Args:
        snapshot_id: Snapshot ID to analyze
        
    Returns:
        Type usage statistics
    """
    try:
        stats = TypeDAO.get_type_usage_stats(snapshot_id)
        return {
            "snapshot_id": snapshot_id,
            "type_count": len(stats),
            "types": stats
        }
    except Exception as e:
        logger.error(f"Failed to get type stats for {snapshot_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

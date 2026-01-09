"""
Type Information Data Access Object
Handles persistence and querying of type annotations
"""

from typing import List, Optional, Dict, Any
from src.models import TypeAnnotation
from src.database.neo4j_client import db
import logging

logger = logging.getLogger(__name__)


class TypeDAO:
    """DAO for type annotation operations"""

    @staticmethod
    def batch_create_types(types: List[TypeAnnotation]):
        """Batch insert type annotations into Neo4j"""
        if not types:
            return

        import json

        # Prepare data for batch insert
        type_data = [
            {
                "type_id": t.type_id,
                "snapshot_id": t.snapshot_id,
                "symbol_id": t.symbol_id,
                "type_name": t.type_name,
                "type_category": t.type_category.value,
                "is_optional": t.is_optional,
                "is_array": t.is_array,
                "generic_params": t.generic_params,
                "meta": json.dumps(t.meta) if t.meta else "{}",
            }
            for t in types
        ]

        query = """
        UNWIND $types AS type
        CREATE (t:TypeAnnotation {
            type_id: type.type_id,
            snapshot_id: type.snapshot_id,
            symbol_id: type.symbol_id,
            type_name: type.type_name,
            type_category: type.type_category,
            is_optional: type.is_optional,
            is_array: type.is_array,
            generic_params: type.generic_params,
            meta: type.meta
        })
        WITH t, type
        MATCH (s:Symbol {symbol_id: type.symbol_id})
        CREATE (s)-[:HAS_TYPE]->(t)
        """

        with db.session() as session:
            session.run(query, types=type_data)

        logger.info(f"Batch created {len(types)} type annotations")

    @staticmethod
    def get_symbol_type(symbol_id: str) -> Optional[Dict[str, Any]]:
        """Get type annotation for a symbol"""

        query = """
        MATCH (s:Symbol {symbol_id: $symbol_id})-[:HAS_TYPE]->(t:TypeAnnotation)
        RETURN t.type_id as type_id, t.type_name as type_name,
               t.type_category as type_category, t.is_optional as is_optional,
               t.is_array as is_array, t.generic_params as generic_params
        """

        with db.session() as session:
            result = session.run(query, symbol_id=symbol_id)
            record = result.single()
            return dict(record) if record else None

    @staticmethod
    def find_symbols_by_type(snapshot_id: str, type_name: str) -> List[Dict[str, Any]]:
        """Find all symbols with a specific type"""

        query = """
        MATCH (s:Symbol {snapshot_id: $snapshot_id})-[:HAS_TYPE]->(t:TypeAnnotation)
        WHERE t.type_name = $type_name
        RETURN s.symbol_id as symbol_id, s.name as name, s.kind as kind,
               s.qualname as qualname
        """

        with db.session() as session:
            result = session.run(query, snapshot_id=snapshot_id, type_name=type_name)
            return [dict(record) for record in result]

    @staticmethod
    def get_type_usage_stats(snapshot_id: str) -> List[Dict[str, Any]]:
        """Get statistics on type usage in a snapshot"""

        query = """
        MATCH (s:Symbol {snapshot_id: $snapshot_id})-[:HAS_TYPE]->(t:TypeAnnotation)
        RETURN t.type_name as type_name, t.type_category as category,
               count(s) as usage_count
        ORDER BY usage_count DESC
        LIMIT 50
        """

        with db.session() as session:
            result = session.run(query, snapshot_id=snapshot_id)
            return [dict(record) for record in result]

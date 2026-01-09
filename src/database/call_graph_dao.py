"""
Call Graph Data Access Object
Handles persistence and querying of function call relationships
"""

from typing import List, Dict, Any
from src.models import CallSite
from src.database.neo4j_client import db
import logging

logger = logging.getLogger(__name__)


class CallGraphDAO:
    """DAO for call graph operations"""

    @staticmethod
    def batch_create_call_sites(call_sites: List[CallSite]):
        """Batch insert call sites into Neo4j"""
        if not call_sites:
            return

        import json

        # Prepare data for batch insert
        call_data = [
            {
                "call_id": cs.call_id,
                "snapshot_id": cs.snapshot_id,
                "caller_symbol_id": cs.caller_symbol_id,
                "callee_name": cs.callee_name,
                "line_number": cs.line_number,
                "is_resolved": cs.is_resolved,
                "call_type": cs.call_type.value,
                "meta": json.dumps(cs.meta) if cs.meta else "{}",
            }
            for cs in call_sites
        ]

        query = """
        UNWIND $calls AS call
        CREATE (c:CallSite {
            call_id: call.call_id,
            snapshot_id: call.snapshot_id,
            caller_symbol_id: call.caller_symbol_id,
            callee_name: call.callee_name,
            line_number: call.line_number,
            is_resolved: call.is_resolved,
            call_type: call.call_type,
            meta: call.meta
        })
        WITH c, call
        MATCH (caller:Symbol {symbol_id: call.caller_symbol_id})
        CREATE (caller)-[:CALLS]->(c)
        """

        with db.session() as session:
            session.run(query, calls=call_data)

        logger.info(f"Batch created {len(call_sites)} call sites")

    @staticmethod
    def resolve_call_sites(snapshot_id: str):
        """Resolve call sites to actual symbols and create RESOLVES_TO relationships"""

        query = """
        MATCH (c:CallSite {snapshot_id: $snapshot_id, is_resolved: false})
        MATCH (callee:Symbol {snapshot_id: $snapshot_id})
        WHERE callee.name = c.callee_name OR callee.qualname = c.callee_name
        CREATE (c)-[:RESOLVES_TO]->(callee)
        SET c.is_resolved = true
        RETURN count(c) as resolved_count
        """

        with db.session() as session:
            result = session.run(query, snapshot_id=snapshot_id)
            record = result.single()
            if record:
                logger.info(f"Resolved {record['resolved_count']} call sites")

    @staticmethod
    def get_callers(symbol_id: str) -> List[Dict[str, Any]]:
        """Get all symbols that call this symbol"""

        query = """
        MATCH (caller:Symbol)-[:CALLS]->(c:CallSite)-[:RESOLVES_TO]->(callee:Symbol {symbol_id: $symbol_id})
        RETURN caller.symbol_id as symbol_id, caller.name as name, 
               caller.kind as kind, c.line_number as call_line
        """

        with db.session() as session:
            result = session.run(query, symbol_id=symbol_id)
            return [dict(record) for record in result]

    @staticmethod
    def get_callees(symbol_id: str) -> List[Dict[str, Any]]:
        """Get all symbols called by this symbol"""

        query = """
        MATCH (caller:Symbol {symbol_id: $symbol_id})-[:CALLS]->(c:CallSite)-[:RESOLVES_TO]->(callee:Symbol)
        RETURN callee.symbol_id as symbol_id, callee.name as name,
               callee.kind as kind, c.line_number as call_line
        """

        with db.session() as session:
            result = session.run(query, symbol_id=symbol_id)
            return [dict(record) for record in result]

    @staticmethod
    def get_call_graph(symbol_id: str, depth: int = 2) -> Dict[str, Any]:
        """Get call graph centered on this symbol"""

        # Build query with depth as literal (Neo4j doesn't allow parameters in range)
        query = f"""
        MATCH path = (s:Symbol {{symbol_id: $symbol_id}})-[:CALLS*1..{depth}]->(:CallSite)-[:RESOLVES_TO]->(target:Symbol)
        RETURN path
        LIMIT 100
        """

        with db.session() as session:
            result = session.run(query, symbol_id=symbol_id)
            paths = [record["path"] for record in result]

            # Build graph structure
            nodes = {}
            edges = []

            for path in paths:
                for node in path.nodes:
                    if "symbol_id" in node:
                        nodes[node["symbol_id"]] = {
                            "id": node["symbol_id"],
                            "name": node.get("name"),
                            "kind": node.get("kind"),
                        }

                for rel in path.relationships:
                    edges.append(
                        {
                            "source": rel.start_node["symbol_id"],
                            "target": rel.end_node.get("symbol_id"),
                            "type": rel.type,
                        }
                    )

            return {"nodes": list(nodes.values()), "edges": edges}

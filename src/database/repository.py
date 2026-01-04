"""
Repository Data Access Layer - Neo4j Operations
"""
from typing import Optional, List, Dict, Any
import logging
import json
from datetime import datetime

from src.database import db
from src.models import Repo, Snapshot, File, Symbol, Endpoint, SnapshotStatus, Import

logger = logging.getLogger(__name__)


def convert_neo4j_types(data: Dict[str, Any]) -> Dict[str, Any]:
    """Convert Neo4j types to Python types for Pydantic compatibility
    
    Args:
        data: Dictionary with Neo4j types
        
    Returns:
        Dictionary with Python types
    """
    converted = {}
    for key, value in data.items():
        # Convert Neo4j DateTime to Python datetime
        if hasattr(value, 'to_native'):
            converted[key] = value.to_native()
        # Parse JSON strings back to dicts
        elif key in ['lang_profile', 'meta'] and isinstance(value, str):
            try:
                converted[key] = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                converted[key] = value
        else:
            converted[key] = value
    return converted


class RepositoryDAO:
    """Data Access Object for Repository operations"""
    
    @staticmethod
    def create_repo(repo: Repo) -> Repo:
        """Create a new repository node
        
        Args:
            repo: Repo model instance
            
        Returns:
            Created Repo instance
        """
        query = """
        CREATE (r:Repo {
            repo_id: $repo_id,
            name: $name,
            source_type: $source_type,
            remote_url: $remote_url,
            created_at: datetime($created_at)
        })
        RETURN r
        """
        params = {
            "repo_id": repo.repo_id,
            "name": repo.name,
            "source_type": repo.source_type.value,
            "remote_url": repo.remote_url,
            "created_at": repo.created_at.isoformat()
        }
        
        result = db.execute_write(query, params)
        logger.info(f"Created repository: {repo.name} ({repo.repo_id})")
        return repo
    
    @staticmethod
    def get_repo(repo_id: str) -> Optional[Repo]:
        """Get repository by ID
        
        Args:
            repo_id: Repository ID
            
        Returns:
            Repo instance or None
        """
        query = """
        MATCH (r:Repo {repo_id: $repo_id})
        RETURN r
        """
        result = db.execute_query(query, {"repo_id": repo_id})
        
        if not result:
            return None
        
        node = convert_neo4j_types(result[0]["r"])
        return Repo(**node)
    
    @staticmethod
    def list_repos() -> List[Repo]:
        """List all repositories
        
        Returns:
            List of Repo instances
        """
        query = "MATCH (r:Repo) RETURN r ORDER BY r.created_at DESC"
        result = db.execute_query(query)
        return [Repo(**convert_neo4j_types(record["r"])) for record in result]


class SnapshotDAO:
    """Data Access Object for Snapshot operations"""
    
    @staticmethod
    def create_snapshot(snapshot: Snapshot) -> Snapshot:
        """Create a new snapshot and link to repository
        
        Args:
            snapshot: Snapshot model instance
            
        Returns:
            Created Snapshot instance
        """
        query = """
        MATCH (r:Repo {repo_id: $repo_id})
        CREATE (s:Snapshot {
            snapshot_id: $snapshot_id,
            repo_id: $repo_id,
            commit_hash: $commit_hash,
            status: $status,
            lang_profile: $lang_profile,
            config_fingerprint: $config_fingerprint,
            created_at: datetime($created_at)
        })
        CREATE (r)-[:HAS_SNAPSHOT]->(s)
        RETURN s
        """
        params = {
            "repo_id": snapshot.repo_id,
            "snapshot_id": snapshot.snapshot_id,
            "commit_hash": snapshot.commit_hash,
            "status": snapshot.status.value,
            "lang_profile": json.dumps(snapshot.lang_profile),
            "config_fingerprint": snapshot.config_fingerprint,
            "created_at": snapshot.created_at.isoformat()
        }
        
        result = db.execute_write(query, params)
        logger.info(f"Created snapshot: {snapshot.snapshot_id}")
        return snapshot
    
    @staticmethod
    def update_snapshot_status(snapshot_id: str, status: SnapshotStatus) -> None:
        """Update snapshot status
        
        Args:
            snapshot_id: Snapshot ID
            status: New status
        """
        query = """
        MATCH (s:Snapshot {snapshot_id: $snapshot_id})
        SET s.status = $status
        """
        db.execute_write(query, {"snapshot_id": snapshot_id, "status": status.value})
        logger.info(f"Updated snapshot {snapshot_id} status to {status.value}")
    
    @staticmethod
    def get_snapshot(snapshot_id: str) -> Optional[Snapshot]:
        """Get snapshot by ID
        
        Args:
            snapshot_id: Snapshot ID
            
        Returns:
            Snapshot instance or None
        """
        query = """
        MATCH (s:Snapshot {snapshot_id: $snapshot_id})
        RETURN s
        """
        result = db.execute_query(query, {"snapshot_id": snapshot_id})
        
        if not result:
            return None
        
        node = convert_neo4j_types(result[0]["s"])
        return Snapshot(**node)
    
    @staticmethod
    def list_snapshots(repo_id: str) -> List[Snapshot]:
        """List all snapshots for a repository
        
        Args:
            repo_id: Repository ID
            
        Returns:
            List of Snapshot instances
        """
        query = """
        MATCH (r:Repo {repo_id: $repo_id})-[:HAS_SNAPSHOT]->(s:Snapshot)
        RETURN s ORDER BY s.created_at DESC
        """
        result = db.execute_query(query, {"repo_id": repo_id})
        return [Snapshot(**convert_neo4j_types(record["s"])) for record in result]


class FileDAO:
    """Data Access Object for File operations"""
    
    @staticmethod
    def create_file(file: File) -> File:
        """Create a new file node and link to snapshot
        
        Args:
            file: File model instance
            
        Returns:
            Created File instance
        """
        query = """
        MATCH (s:Snapshot {snapshot_id: $snapshot_id})
        CREATE (f:File {
            file_id: $file_id,
            snapshot_id: $snapshot_id,
            path: $path,
            language: $language,
            sha256: $sha256,
            loc: $loc,
            is_test: $is_test,
            tags: $tags
        })
        CREATE (s)-[:CONTAINS_FILE]->(f)
        RETURN f
        """
        params = {
            "snapshot_id": file.snapshot_id,
            "file_id": file.file_id,
            "path": file.path,
            "language": file.language,
            "sha256": file.sha256,
            "loc": file.loc,
            "is_test": file.is_test,
            "tags": file.tags
        }
        
        db.execute_write(query, params)
        logger.debug(f"Created file: {file.path}")
        return file
    
    @staticmethod
    def batch_create_files(files: List[File]) -> None:
        """Batch create multiple files
        
        Args:
            files: List of File instances
        """
        if not files:
            return
        
        query = """
        UNWIND $files AS file_data
        MATCH (s:Snapshot {snapshot_id: file_data.snapshot_id})
        CREATE (f:File {
            file_id: file_data.file_id,
            snapshot_id: file_data.snapshot_id,
            path: file_data.path,
            language: file_data.language,
            sha256: file_data.sha256,
            loc: file_data.loc,
            is_test: file_data.is_test,
            tags: file_data.tags
        })
        CREATE (s)-[:CONTAINS_FILE]->(f)
        """
        
        files_data = [
            {
                "file_id": f.file_id,
                "snapshot_id": f.snapshot_id,
                "path": f.path,
                "language": f.language,
                "sha256": f.sha256,
                "loc": f.loc,
                "is_test": f.is_test,
                "tags": f.tags
            }
            for f in files
        ]
        
        db.execute_write(query, {"files": files_data})
        logger.info(f"Batch created {len(files)} files")
    
    @staticmethod
    def get_files_by_snapshot(snapshot_id: str) -> List[File]:
        """Get all files in a snapshot
        
        Args:
            snapshot_id: Snapshot ID
            
        Returns:
            List of File instances
        """
        query = """
        MATCH (s:Snapshot {snapshot_id: $snapshot_id})-[:CONTAINS_FILE]->(f:File)
        RETURN f ORDER BY f.path
        """
        result = db.execute_query(query, {"snapshot_id": snapshot_id})
        return [File(**convert_neo4j_types(record["f"])) for record in result]


class SymbolDAO:
    """Data Access Object for Symbol operations"""
    
    @staticmethod
    def create_symbol(symbol: Symbol) -> Symbol:
        """Create a new symbol node
        
        Args:
            symbol: Symbol model instance
            
        Returns:
            Created Symbol instance
        """
        query = """
        MATCH (f:File {file_id: $file_id})
        CREATE (sym:Symbol {
            symbol_id: $symbol_id,
            snapshot_id: $snapshot_id,
            file_id: $file_id,
            kind: $kind,
            name: $name,
            qualname: $qualname,
            signature: $signature,
            start_line: $start_line,
            end_line: $end_line,
            meta: $meta
        })
        CREATE (f)-[:DEFINES_SYMBOL]->(sym)
        RETURN sym
        """
        params = {
            "file_id": symbol.file_id,
            "symbol_id": symbol.symbol_id,
            "snapshot_id": symbol.snapshot_id,
            "kind": symbol.kind.value,
            "name": symbol.name,
            "qualname": symbol.qualname,
            "signature": symbol.signature,
            "start_line": symbol.start_line,
            "end_line": symbol.end_line,
            "meta": json.dumps(symbol.meta)
        }
        
        db.execute_write(query, params)
        logger.debug(f"Created symbol: {symbol.qualname}")
        return symbol
    
    @staticmethod
    def batch_create_symbols(symbols: List[Symbol]) -> None:
        """Batch create multiple symbols
        
        Args:
            symbols: List of Symbol instances
        """
        if not symbols:
            return
        
        query = """
        UNWIND $symbols AS sym_data
        MATCH (f:File {file_id: sym_data.file_id})
        CREATE (sym:Symbol {
            symbol_id: sym_data.symbol_id,
            snapshot_id: sym_data.snapshot_id,
            file_id: sym_data.file_id,
            kind: sym_data.kind,
            name: sym_data.name,
            qualname: sym_data.qualname,
            signature: sym_data.signature,
            start_line: sym_data.start_line,
            end_line: sym_data.end_line,
            meta: sym_data.meta
        })
        CREATE (f)-[:DEFINES_SYMBOL]->(sym)
        """
        
        symbols_data = [
            {
                "symbol_id": s.symbol_id,
                "snapshot_id": s.snapshot_id,
                "file_id": s.file_id,
                "kind": s.kind.value,
                "name": s.name,
                "qualname": s.qualname,
                "signature": s.signature,
                "start_line": s.start_line,
                "end_line": s.end_line,
                "meta": json.dumps(s.meta)
            }
            for s in symbols
        ]
        
        db.execute_write(query, {"symbols": symbols_data})
        logger.info(f"Batch created {len(symbols)} symbols")


class ImportDAO:
    """Data Access Object for Import operations"""
    
    @staticmethod
    def batch_create_imports(imports: List[Import]) -> None:
        """Batch create import nodes
        
        Args:
            imports: List of Import instances
        """
        if not imports:
            return
        
        query = """
        UNWIND $imports AS imp_data
        MATCH (f:File {file_id: imp_data.file_id})
        CREATE (i:Import {
            import_id: imp_data.import_id,
            snapshot_id: imp_data.snapshot_id,
            file_id: imp_data.file_id,
            module: imp_data.module,
            imported_names: imp_data.imported_names,
            alias: imp_data.alias,
            is_relative: imp_data.is_relative,
            line_number: imp_data.line_number
        })
        CREATE (f)-[:HAS_IMPORT]->(i)
        """
        
        imports_data = [
            {
                "import_id": i.import_id,
                "snapshot_id": i.snapshot_id,
                "file_id": i.file_id,
                "module": i.module,
                "imported_names": json.dumps(i.imported_names),
                "alias": i.alias,
                "is_relative": i.is_relative,
                "line_number": i.line_number
            }
            for i in imports
        ]
        
        db.execute_write(query, {"imports": imports_data})
        logger.info(f"Batch created {len(imports)} imports")
    
    @staticmethod
    def create_import_edge(
        src_file_id: str,
        dst_file_id: str,
        module_name: str,
        line_number: int
    ) -> None:
        """Create IMPORTS relationship between files
        
        Args:
            src_file_id: Source file ID
            dst_file_id: Destination file ID
            module_name: Module being imported
            line_number: Line number of import
        """
        query = """
        MATCH (src:File {file_id: $src_file_id})
        MATCH (dst:File {file_id: $dst_file_id})
        MERGE (src)-[r:IMPORTS {module: $module_name}]->(dst)
        ON CREATE SET r.line_number = $line_number
        """
        
        db.execute_write(query, {
            "src_file_id": src_file_id,
            "dst_file_id": dst_file_id,
            "module_name": module_name,
            "line_number": line_number
        })
    
    @staticmethod
    def batch_create_import_edges(edges: List[Dict[str, Any]]) -> None:
        """Batch create import edges
        
        Args:
            edges: List of edge dictionaries with src_file_id, dst_file_id, module, line
        """
        if not edges:
            return
        
        query = """
        UNWIND $edges AS edge
        MATCH (src:File {file_id: edge.src_file_id})
        MATCH (dst:File {file_id: edge.dst_file_id})
        MERGE (src)-[r:IMPORTS {module: edge.module}]->(dst)
        ON CREATE SET r.line_number = edge.line_number
        """
        
        db.execute_write(query, {"edges": edges})
        logger.info(f"Batch created {len(edges)} import edges")
    
    @staticmethod
    def get_file_imports(file_id: str) -> List[Dict[str, Any]]:
        """Get all imports for a file
        
        Args:
            file_id: File ID
            
        Returns:
            List of import dictionaries
        """
        query = """
        MATCH (f:File {file_id: $file_id})-[:IMPORTS]->(imported:File)
        RETURN imported.file_id as file_id, imported.path as path
        """
        return db.execute_query(query, {"file_id": file_id})
    
    @staticmethod
    def get_import_graph(snapshot_id: str) -> List[Dict[str, Any]]:
        """Get the complete import dependency graph
        
        Args:
            snapshot_id: Snapshot ID
            
        Returns:
            List of import relationships
        """
        query = """
        MATCH (src:File)-[r:IMPORTS]->(dst:File)
        WHERE src.snapshot_id = $snapshot_id
        RETURN src.path as source, dst.path as target, r.module as module
        ORDER BY src.path
        """
        return db.execute_query(query, {"snapshot_id": snapshot_id})
    
    @staticmethod
    def get_file_dependencies(snapshot_id: str, file_path: str) -> List[Dict[str, Any]]:
        """Get all files that depend on this file (reverse dependencies)
        
        Args:
            snapshot_id: Snapshot ID
            file_path: File path to find dependencies for
            
        Returns:
            List of dependent files
        """
        query = """
        MATCH (dependent:File)-[:IMPORTS]->(f:File {path: $file_path})
        WHERE f.snapshot_id = $snapshot_id
        RETURN dependent.path as dependent_file, dependent.file_id as file_id
        ORDER BY dependent.path
        """
        return db.execute_query(query, {
            "snapshot_id": snapshot_id,
            "file_path": file_path
        })

